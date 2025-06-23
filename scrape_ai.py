# Standard lib
import asyncio
import json
import os
from datetime import datetime
from typing import List, Optional, TypeVar, Type

# Third-party
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv
from urllib.parse import urljoin

# Local
from nav import Navigator

class Property(BaseModel):
    title: str
    amenities: str
    state: str
    address: str
    floorplans_url: Optional[str] = Field(
        description="URL for the floor-plans of this specific property")


class Site(BaseModel):  
    deals: str
    amenities: str
    state: Optional[str] = Field(
        description="State where this apartment complex is located")
    address: Optional[str] = Field(description="Street address")
    floorplans_url: str = Field(
        description="URL for the *site's* general floor-plans page")
    properties: List[Property] = Field(
        default_factory=list,
        description="All individual buildings / addresses that belong to this site")


class Listing(BaseModel):
    listname: str = Field(description="Name of the listing")
    bedrooms: int = Field(description="Number of bedrooms")
    bathrooms: int = Field(description="Number of bathrooms")
    sqft: int = Field(description="Square footage")
    shared_room: bool = Field(description="Whether the listing is a shared room")


# ---------------------------------------------------------------------------
#   Listing-level models (for later steps)
# ---------------------------------------------------------------------------

class ListingSnapshot(BaseModel):
    availability: str
    price: str
    price_per_sqft: str
    description: str
    original_price: str
    deals: str


# ---------------------------------------------------------------------------
#   Floor-plan container detection
# ---------------------------------------------------------------------------

class ContainerSelector(BaseModel):
    """Return value for :pyfunc:`init_container`.

    Only a single field – ``selector`` – which contains a CSS selector that
    matches *each* floor-plan card / container on the page. The selector must
    include **all** relevant information for an individual listing (price,
    beds, baths, sqft, availability, deals, …).
    """

    selector: str = Field(
        description=(
            "CSS selector that, when applied with querySelectorAll, returns one"
            " element per floor-plan listing. Use attribute starts-with/ends-with"
            " selectors (e.g. div[id^='fp-']) or :is(), :where(), etc. when"
            " necessary to handle dynamic ids such as 'fp-124', 'fp-245'."
        )
    )


T = TypeVar("T", bound=BaseModel)

def coerce_to(model: Type[T], raw) -> T:
    """
    Convert *raw* (Pydantic model | dict | JSON-string) into *model*.

    Raises ValidationError / JSONDecodeError if the payload is irreparably bad.
    """
    if isinstance(raw, model):
        return raw
    if isinstance(raw, str):
        return model.model_validate_json(raw)
    return model.model_validate(raw)

# --- OpenAI client ----------------------------------------------------------

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# --- Core helper -----------------------------------------------------------


async def ai_init(url: str, text: str) -> Site:
    """Return a populated `Site` object after asking GPT to analyse *url*.

    GPT is instructed to decide which of these situations applies:
      1. The current page already shows all floor-plans for the site.
      2. The current page links to a dedicated floor-plans page.
      3. The website hosts multiple properties, each with its own floor-plans
         page (return those URLs under properties[*].floorplans_url).

    """


    prompt = (
        "You are given the raw HTML of a real-estate website page together with its URL.\n\n"
        f"Current URL: {url}\n"
        f"HTML: {text}\n\n"
        "Based on the markup, decide which of the following scenarios applies and respond using **exactly** the JSON schema below.\n\n"
        "Scenario rules (mutually exclusive) – return **either** a non-empty `floorplans_url` **or** a non-empty `properties` list, never both:\n"
        "1. If *this* page already lists all floor-plans for the whole site, set `floorplans_url` to the **current URL** and leave `properties` empty.\n"
        "2. If there is a single link that points to a page containing all floor-plans, set `floorplans_url` to that link and leave `properties` empty.\n"
        "3. Otherwise, if the website contains several *distinct buildings* (each with its own listings / floor-plans page), return those links in `properties`.\n"
        "   • Do **not** treat individual floor-plan types such as '1-Bedroom', '2-Bed 2-Bath', 'Studio', etc. as properties.\n"
        "   • Only add to `properties` if you find **two or more** real buildings. If there is only one, fall back to rule 2 and populate `floorplans_url` instead.\n"
        "   • For each valid property, fill only the `floorplans_url` field (other fields may be left blank). Set the top-level `floorplans_url` to an empty string when you return `properties`.\n"
        "4. If none of the above apply, return an empty object.\n\n"
        "Important formatting rules:\n"
        "• If a link is a *relative* path (e.g. \"/floorplans/\"), convert it to an **absolute URL** by prefixing it with the scheme and host of the current URL before returning it.\n"
        "• Ensure the final output conforms to the provided JSON schema.\n"
    )

    init_response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are an expert web-scraping assistant"
            },
            {"role": "user", "content": prompt},
        ],
        response_format=Site
    )

    # The library is still experimental – depending on the version
    # `message.content` may be a raw JSON string, a Python ``dict`` or
    # an already-parsed ``Site`` instance.  Normalise to a ``Site``.

    raw_content = init_response.choices[0].message.content  # type: ignore

    site = coerce_to(Site, raw_content)

    # Helper to absolutise links.
    def absolutise(link: Optional[str]) -> Optional[str]:
        if link and not link.startswith("http"):
            return urljoin(url, link)
        return link

    # Convert main floor-plans URL (if present).
    site.floorplans_url = absolutise(site.floorplans_url) or ""

    # Convert every property link to absolute.
    for prop in site.properties:
        prop.floorplans_url = absolutise(prop.floorplans_url)

    # --------------------------------------------------------------
    # Heuristics to clean up incorrectly detected "properties"
    # --------------------------------------------------------------
    import re

    def looks_like_floorplan(title: str) -> bool:
        """Return True if *title* resembles a floor-plan label, e.g. '2-Bedroom'."""
        pattern = re.compile(r"(\b|_)(\d+|studio)[\s\-]*(bed|br|bedroom|bdrm)", re.I)
        return bool(pattern.search(title))

    # Drop any entries that look like individual floor-plans rather than buildings.
    site.properties = [p for p in site.properties if not looks_like_floorplan(p.title or "")]

    # If, after filtering, we ended up with 0 or 1 property, collapse back to scenario 2.
    if len(site.properties) <= 1:
        # Pick a URL to promote: either the (sole) property link or keep the existing site URL.
        promoted = ""
        if site.properties:
            promoted = site.properties[0].floorplans_url or ""
        if not promoted:
            promoted = site.floorplans_url

        site.floorplans_url = promoted or ""
        site.properties = []

    # Enforce mutual exclusivity just in case the model violated it.
    if site.properties:
        site.floorplans_url = ""
    else:
        site.properties = []

    return site

async def init_container(url: str, text: str) -> str:
    """Given the raw HTML of a *floor-plans page*, return a CSS selector that
    identifies the container element for *each* individual floor-plan.

    The goal is to make downstream scraping easy: the selector should surround
    as much information as possible for one listing (price, beds, baths, sqft,
    availability, deals, etc.).  Dynamic ids that differ only by numeric parts
    (e.g. ``#fp-124`` vs. ``#fp-245``) *are allowed*, in which case prefer a
    *pattern-based* selector like ``div[id^='fp-']``.
    """

    prompt = (
        "You are given the HTML of a *floor-plans* page for an apartment site.\n\n"
        f"Current URL: {url}\n"
        f"HTML: {text}\n\n"
        "Find a single CSS selector that selects **one element per floor-plan" \
        " listing**, where each selected element contains as much detail as\n" \
        " possible about that listing (beds, baths, price, availability, sqft,\n" \
        " deals, etc.).\n\n"
        "Requirements:\n"
        "• The selector MUST match *every* listing and nothing else.\n"
        "• If the container elements have dynamic ids/prefixes (e.g. fp-124,\n"
        "  fp-245) use an attribute prefix selector such as `div[id^='fp-']`.\n"
        "• Prefer concise selectors with class/id attributes; avoid selectors\n"
        "  that rely on absolute DOM hierarchy positions unless necessary.\n"
        "• Output ONLY the selector string in your reply. No markdown, no extra\n"
        "  text.\n"
    )

    completion = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert web-scraping assistant"},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "text"}  # raw text; we post-process into the model
    )

    raw_selector = completion.choices[0].message.content.strip()

    # Validate minimal sanity: non-empty and no whitespace-only string.
    if not raw_selector:
        raise ValueError("GPT did not return a selector")

    # Wrap into ContainerSelector for type safety (will raise if invalid).
    selector_obj = ContainerSelector(selector=raw_selector)

    return selector_obj.selector



async def ai_parse_listings(url: str, containers: List[str]) -> List[Listing]:
    """Return a list of Listing objects extracted by GPT from *containers*.

    Each element in *containers* is the raw HTML for one floor-plan card.
    """

    joined = "\n\n--- CONTAINER ---\n\n".join(containers)

    prompt = (
        "You are given HTML snippets, each representing a single floor-plan listing "
        "on a real-estate website (URL shown below). Parse every snippet and build "
        "a list of Listing objects that follow the provided schema exactly. "
        "Return ONLY the list—no extra keys or wrapper.\n\n"
        f"Current URL: {url}\n\n"
        "HTML snippets (one per listing, separated by \"--- CONTAINER ---\"):\n\n"
        f"{joined}\n\n"
    )

    init_response = await asyncio.to_thread(
        client.beta.chat.completions.parse,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert web-scraping assistant"},
            {"role": "user", "content": prompt},
        ],
        response_format=ListingsWrapper,
    )

    wrapper = coerce_to(ListingsWrapper, init_response.choices[0].message.content)
    return wrapper.listings


class ListingsWrapper(BaseModel):
    listings: List[Listing]
 