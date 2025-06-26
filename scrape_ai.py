# Standard lib
import asyncio
import json
import os
from datetime import datetime
from typing import List, Optional, TypeVar, Type
import re

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
    amenities: Optional[str] = Field(description="Any amenities the listing has")


class ListingSnapshot(BaseModel):
    listname: str = Field(description="Exactly the same listname used in the parent Listing table (acts as foreign-key lookup)")
    availability: str = Field(description="Availability of the listing")
    price: str = Field(description="Current price OR price range of the listing")
    pre_deal_price: Optional[str] = Field(description="Price of the listing before any deals, may be slashed through")
    deals: Optional[str] = Field(description="Any deals the listing has, may be sign up deals, move in deals, etc.")


class SelectorList(BaseModel):
    """Wrapper returned by GPT containing up to three candidate selectors."""

    selectors: List[str] = Field(
        min_length=1, max_length=3,
        description="Ranked CSS selectors, best first."
    )


# Generic coercion helper used across parsers
# Make a return from AI model into BaseModel type
T = TypeVar("T", bound=BaseModel)
def coerce_to(model: Type[T], raw) -> T:
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
        "2. If there is a single link that points to a dedicated floor-plans page, choose the **shortest** link that ends with `/floorplans/` (relative paths like `/floorplans/` or `/apartments/floorplans/`), preferring those over longer links that include filenames such as `.aspx`. Set `floorplans_url` to that link and leave `properties` empty.\n"
        "3. Otherwise, if the website contains several *distinct buildings* (each with its own listings / floor-plans page), return those links in `properties`.\n"
        "   • Do **not** treat individual floor-plan types such as '1-Bedroom', '2-Bed 2-Bath', 'Studio', etc. as properties.\n"
        "   • Only add to `properties` if you find **two or more** real buildings. If there is only one, fall back to rule 2 and populate `floorplans_url` instead.\n"
        "   • For each valid property, fill only the `floorplans_url` field (other fields may be left blank). Set the top-level `floorplans_url` to an empty string when you return `properties`.\n"
        "   • **Heuristic**: Any URL whose path contains the word 'floorplan' or 'floorplans' almost certainly points to the site's floor-plans page—treat it according to rule 2 and **never** put it under `properties`.\n"
        "4. If none of the above apply, return an empty object.\n\n"
        "Important formatting rules:\n"
        "• If a link is a *relative* path (e.g. \"/floorplans/\"), convert it to an **absolute URL** by prefixing it with the scheme and host of the current URL before returning it.\n"
        "• Ensure the final output conforms to the provided JSON schema.\n"
        "• If the page lacks suitable class names but you find that many listing\n"
        "  elements have IDs whose static prefix is followed by digits (e.g. \n"
        "  \"eg-3-post-id-15392_7723\"), build the selector with an attribute prefix\n"
        "  selector: [id^='eg-3-post-id-'].\n"
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

    raw_content = init_response.choices[0].message.content

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

    # Enforce mutual exclusivity for floorplan v properties just in case the model violated it.
    if site.properties:
        site.floorplans_url = ""
    else:
        site.properties = []

    return site

async def init_container(url: str, text: str) -> List[str]:
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
        "Your task: Propose up to **three** CSS selectors (ranked best-first) that, when applied via \n"
        "`querySelectorAll`, each return **one element per floor-plan listing**.\n\n"
        "Selector rules:\n"
        "• Must capture as much detail for a single listing as possible (beds, price, sqft, etc.).\n"
        "• If the elements have numeric IDs like `fp-124`, `fp-245`, use attribute patterns: `div[id^='fp-']`.\n"
        "• DO NOT prefix element names with a dot (❌ `.div.foo`, ✅ `div.foo`).\n"
        "• DO NOT prefix element names with a dot when matching ids (❌ `.a.bar`).\n"
        "• Use single quotes inside attribute selectors.\n"
        "• Return selectors in a JSON object of this exact shape:\n"
        "  { \"selectors\": [ \"<css1>\", \"<css2>\", \"<css3>\" ] }\n"
        "  – Provide 1-3 entries, no additional keys, no markdown.\n\n"
        "HTML (truncated):\n" + text[:20000]
    )

    init_response = await asyncio.to_thread(
        client.beta.chat.completions.parse,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert web-scraping assistant"},
            {"role": "user", "content": prompt},
        ],
        response_format=SelectorList,
    )

    raw = init_response.choices[0].message.content  # type: ignore
    return coerce_to(SelectorList, raw).selectors



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


async def ai_parse_listing_snapshots(url: str, containers: List[str]) -> List[ListingSnapshot]:
    """Return a ListingSnapshot object extracted by GPT from *container*."""

    joined = "\n\n--- CONTAINER ---\n\n".join(containers)

    prompt = (
        "You are given HTML snippets, each representing a single floor-plan listing "
        "on a real-estate website (URL shown below). Parse every snippet and build "
        "a list of ListingSnapshot objects that follow the provided schema exactly. "
        "There should be ONLY ONE ListingSnapshot object for each floor-plan listing."
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
        response_format=ListingSnapshotWrapper,
    )

    wrapper = coerce_to(ListingSnapshotWrapper, init_response.choices[0].message.content)
    return wrapper.listing_snapshots
 
class ListingSnapshotWrapper(BaseModel):
    listing_snapshots: List[ListingSnapshot]


# ---------------------------------------------------------------------------
#   Selector post-processing utilities
# ---------------------------------------------------------------------------


def sanitize_selector(selector: str) -> str:
    """Return *selector* with common GPT mistakes fixed.

    Fixes:
    1. Leading dot before element name (".div.foo" -> "div.foo").
    2. Leading dot before element with id/class when element omitted (".a.bar" -> "a.bar").
    3. Strips surrounding whitespace.
    """

    sel = selector.strip()

    # Replace .div or .span etc. at start with div/span
    sel = re.sub(r"^\.([a-zA-Z]+)([.#])", r"\1\2", sel)

    # Replace .element when element is followed by class/id part, `.a.class` -> `a.class`
    sel = re.sub(r"^\.([a-zA-Z][a-zA-Z0-9_-]*)", r"\1", sel)

    sel = sel.replace('"', "'")

    return sel

# --------------------------- heuristic selector ---------------------------

async def heuristic_id_prefix_selector(page) -> Optional[str]:
    """Inspect the DOM and return a prefix-based selector if multiple IDs share it."""

    ids: List[str] = await page.eval_on_selector_all(
        "[id]",
        "els => els.map(e => e.id).slice(0, 500)"  # limit to avoid huge payload
    )

    from collections import Counter

    prefix_counter: Counter[str] = Counter()

    for id_val in ids:
        m = re.match(r"^(.*?post-id-)", id_val)
        if m:
            prefix_counter[m.group(1)] += 1

    if not prefix_counter:
        return None

    prefix, count = prefix_counter.most_common(1)[0]
    if count < 3:
        return None

    return f"[id^='{prefix}']"

