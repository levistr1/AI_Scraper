# Standard lib
import asyncio
import json
import os
from datetime import datetime
from typing import List, Optional

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
    listname: str
    bedrooms: int
    bathrooms: int
    sqft: int
    shared_room: bool


class ListingSnapshot(BaseModel):
    availability: str
    price: str
    price_per_sqft: str
    description: str
    original_price: str
    deals: str


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

    site = parse_raw_content(raw_content, url)

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


def parse_raw_content(raw_content: str, url: str) -> Site:
    if isinstance(raw_content, Site):
        return raw_content
    else:
        try:
            # If we got a *string*, try JSON first.
            if isinstance(raw_content, str):
                return Site.model_validate_json(raw_content)
            # If we got a *dict* (or other mapping-like), validate directly.
            else:
                return Site.model_validate(raw_content)
        except Exception as exc:
            # Surface a clear error message for easier debugging.
            raise ValueError(
                "Failed to parse response from OpenAI into `Site` model: "
                f"{exc}. Raw content: {raw_content!r}"
            ) from exc