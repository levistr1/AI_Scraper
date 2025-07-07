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
from config import common_container_patterns, container_characteristics

# class Property(BaseModel):
#     title: str
#     amenities: str
#     state: str
#     address: str
#     floorplans_url: Optional[str] = Field(
#         description="URL for the floor-plans of this specific property")


# class Site(BaseModel):  
#     deals: str
#     amenities: str
#     state: Optional[str] = Field(
#         description="State where this apartment complex is located")
#     address: Optional[str] = Field(description="Street address")
#     floorplans_url: str = Field(
#         description="URL for the *site's* general floor-plans page")
#     properties: List[Property] = Field(
#         default_factory=list,
#         description="All individual buildings / addresses that belong to this site")


# class Listing(BaseModel):
#     listname: str = Field(description="Name of the listing")
#     bedrooms: int = Field(description="Number of bedrooms")
#     bathrooms: int = Field(description="Number of bathrooms")
#     sqft: int = Field(description="Square footage")
#     shared_room: bool = Field(description="Whether the listing is a shared room")
#     amenities: Optional[str] = Field(description="Any amenities the listing has")


# class ListingSnapshot(BaseModel):
#     listname: str = Field(description="Exactly the same listname used in the parent Listing table (acts as foreign-key lookup)")
#     availability: str = Field(description="Availability of the listing")
#     price: str = Field(description="Current price OR price range of the listing")
#     pre_deal_price: Optional[str] = Field(description="Price of the listing before any deals, may be slashed through")
#     deals: Optional[str] = Field(description="Any deals the listing has, may be sign up deals, move in deals, etc.")


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


async def ai_init(url: str, text: str, filled: dict) -> dict:
    """Return a populated `Site` object after asking GPT to analyse *url*.

    GPT is instructed to decide which of these situations applies:
      1. The current page already shows all floor-plans for the site.
      2. The current page links to a dedicated floor-plans page.
      3. The website hosts multiple properties, each with its own floor-plans
         page (return those URLs under properties[*].floorplans_url).

    """
    props = {
        "deals": {
            "type": "string"
        },
        "amenities": {
            "type": "string"
        },
        "state": {
            "type": "string",
            "description": "State where this apartment complex is located"
        },
        "address": {
            "type": "string",
            "description": "Street address"
        },
        "floorplans_url": {
            "type": "string",
            "description": "URL for the *site's* general floor-plans page"
        }

    }

    for key in filled.keys():
        props.pop(key, None)

    if not props:
        return {}

    prompt = (
        "You are given the raw HTML of a real-estate website page together with its URL.\n\n"
        f"Current URL: {url}\n"
        f"HTML: {text}\n\n"
        "Based on the markup, decide which of the following scenarios applies and respond using **exactly** the JSON schema below.\n\n"
        "Ensure the final output conforms to the provided JSON schema.\n"
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
        response_format= {
            "type": "json_schema",
            "json_schema": {
                "name": "site",
                "schema": {
                    "description": "Data from a real estate website",
                    "type": "object",
                    "properties": props
                }
            }
        }
    )

    raw_content = init_response.choices[0].message.content
    ai_initialized = json.loads(raw_content)

    try:
        site = ai_initialized.get("properties", {})
        if site:
            print(f"site properties: {site}")
            return site
        else:
            print("no site properties")
            return ai_initialized

    except:
        print("AI could not find site info")
        return {}

async def init_container(url: str, text: str) -> List[str]:
    """Given the raw HTML of a *floor-plans page*, return a CSS selector that
    identifies the container element for *each* individual floor-plan.

    The goal is to make downstream scraping easy: the selector should surround
    as much information as possible for one listing (price, beds, baths, sqft,
    availability, deals, etc.).  Dynamic ids that differ only by numeric parts
    (e.g. ``#fp-124`` vs. ``#fp-245``) *are allowed*, in which case prefer a
    *pattern-based* selector like ``div[id^='fp-']``.
    """
    
    # Create examples string from our successful patterns, organized by type
    class_patterns = [p for p in common_container_patterns if not p.startswith('[')]
    id_patterns = [p for p in common_container_patterns if p.startswith('[id')]
    other_patterns = [p for p in common_container_patterns if p.startswith('[') and not p.startswith('[id')]
    
    pattern_examples = (
        "CLASS-BASED PATTERNS:\n" + "\n".join([f"  • {pattern}" for pattern in class_patterns[:8]]) + "\n\n" +
        "ID-BASED PATTERNS:\n" + "\n".join([f"  • {pattern}" for pattern in id_patterns[:8]]) + "\n\n" +
        "OTHER PATTERNS:\n" + "\n".join([f"  • {pattern}" for pattern in other_patterns[:4]])
    )
    
    characteristics_list = "\n".join([f"  • {char}" for char in container_characteristics])
    
    # Debug: Show what patterns we're sending to AI
    print(f"🤖 Sending proven patterns to AI for {url}")
    print(f"   Class patterns: {len(class_patterns)} (first: {class_patterns[0] if class_patterns else 'none'})")
    print(f"   ID patterns: {len(id_patterns)} (first: {id_patterns[0] if id_patterns else 'none'})")
    print(f"   Other patterns: {len(other_patterns)}")
    print()

    prompt = (
        "You are an expert web scraper analyzing a floor-plans page. Your task is to find CSS selectors that identify individual floor plan listing containers.\n\n"
        
        f"CURRENT URL: {url}\n\n"
        
        "⚠️ CRITICAL: TEST ALL PROVEN PATTERN TYPES ⚠️\n"
        "Before creating custom selectors, systematically check if ANY of these proven patterns work.\n"
        "Each pattern type works on different sites - test ALL types, not just class-based patterns!\n\n"
        
        f"PROVEN SUCCESSFUL PATTERNS:\n{pattern_examples}\n\n"
        
        "PATTERN TESTING STRATEGY:\n"
        "• Test class-based patterns (div.fp-card, div.floorplan, etc.)\n"
        "• Test ID-based patterns ([id^='fp-'], [id^='eg-3-post-id'], etc.)\n"
        "• Test data/other attribute patterns\n"
        "• Only create custom selectors if NO proven patterns work\n"
        "• Different sites use different pattern types - be thorough!\n\n"
        
        "ANALYSIS APPROACH:\n"
        "1. FIRST: Systematically test ALL proven pattern types\n"
        "2. Look for repeating structural patterns that contain floor plan information\n"
        "3. Identify elements that wrap complete listing data together\n"
        "4. Prefer selectors that capture multiple data points per listing\n"
        "5. Avoid overly specific selectors that might break with minor changes\n\n"
        
        "GOOD CONTAINER CHARACTERISTICS (look for elements that contain):\n"
        f"{characteristics_list}\n\n"
        
        "SELECTOR REQUIREMENTS:\n"
        "• Each selector should return ONE element per floor plan listing when using querySelectorAll\n"
        "• PREFER ANY proven patterns over custom selectors\n"
        "• Must capture as much listing detail as possible (beds, baths, sqft, price, etc.)\n"
        "• For numeric IDs like 'fp-124', 'fp-245', use patterns: [id^='fp-']\n"
        "• For complex IDs like 'eg-3-post-id-15392_7723', use: [id^='eg-3-post-id-']\n"
        "• DO NOT prefix elements with dots (❌ '.div.foo' ✅ 'div.foo')\n"
        "• Use single quotes in attribute selectors\n"
        "• Prefer semantic class names over generic ones\n"
        "• Avoid overly complex descendant selectors unless absolutely necessary\n\n"
        
        "AVOID SELECTING:\n"
        "• Navigation elements or page headers\n"
        "• Individual data fields (price only, bedroom count only)\n"
        "• Parent containers that hold ALL listings together\n"
        "• Elements that appear only once on the page\n"
        "• Overly generic selectors like 'div' or '.item'\n"
        "• Complex multi-level descendant selectors when simple ones work\n\n"
        
        "ANALYSIS STEPS:\n"
        "1. Look for class-based patterns: div.fp-card, div.floorplan, div.floor-plan\n"
        "2. Look for ID patterns: [id^='fp-'], [id^='eg-3-post-id'], [id^='floorplan-']\n"
        "3. Look for data attributes: [data-floorplan], [data-unit-type]\n"
        "4. Only if NO proven patterns work, analyze for custom selectors\n"
        "5. Look for class names with 'floor', 'plan', 'unit', 'apartment', 'listing'\n"
        "6. Check for ID patterns with numeric suffixes\n"
        "7. Examine the DOM structure for logical groupings\n"
        "8. Validate each selector would capture complete listing information\n\n"
        
        "RESPONSE FORMAT:\n"
        "Return a JSON object with this exact structure:\n"
        '{ "selectors": ["<best_selector>", "<second_best>", "<third_best>"] }\n'
        "• Provide 1-3 selectors ranked by confidence (best first)\n"
        "• PRIORITIZE any working proven patterns over custom selectors\n"
        "• Include different pattern types if multiple work\n"
        "• No additional keys, no markdown, no explanations\n"
        "• Each selector should be production-ready\n\n"
        
        f"HTML TO ANALYZE:\n{text}"
    )

    init_response = await asyncio.to_thread(
        client.beta.chat.completions.parse,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert web-scraping assistant with deep knowledge of HTML structure and CSS selectors. You excel at finding robust, reliable selectors for apartment listing containers."},
            {"role": "user", "content": prompt},
        ],
        response_format=SelectorList,
    )

    raw = init_response.choices[0].message.content  # type: ignore
    return coerce_to(SelectorList, raw).selectors



async def ai_parse_listings(container: str, filled: dict) -> dict:

    props = {
        "listname": {
            "type": "string",
            "description": "Name of the listing"
        },
        "bedrooms": {
            "type": "string",
            "description": "Number of bedrooms, record INT only"
        },
        "bathrooms": {
            "type": "string",
            "description": "Number of bathrooms, record INT only"
        },
        "sqft": {
            "type": "string",
            "description": "Square feet of the apartment, record INT only"
        }
    }

    for key, value in filled.items():
        if value != None:
            props.pop(key, None)


    if not props:
        print("AI not necessary listings")
        return {}


    prompt = (
        "You are given an HTML snippet representing a single floor-plan listing "
        "on a real-estate website. Parse the snippet and build "
        "a JSON object that follow the provided schema exactly. "
        "Please find the name of the listing"
        "Return ONLY the list—no extra keys or wrapper.\n\n"
        "HTML snippet:\n\n"
        f"{container}\n\n"
    )

    init_response = await asyncio.to_thread(
        client.beta.chat.completions.parse,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert web-scraping assistant"},
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "listing",
                "schema": {
                    "description": "Data from a real estate listing",
                    "type": "object",
                    "properties": props
                }
            }
        }
    )

    raw_content = init_response.choices[0].message.content
    ai_listing = json.loads(raw_content)
    print(ai_listing)

    try:
        listing = ai_listing.get("properties", {})
        if listing:

            return listing
        else:

            return ai_listing
    except:
        print("AI could not find listing info")
        return {}

    

async def ai_parse_listing_snapshots(container: str, filled: dict) -> dict:
    """Return a ListingSnapshot object extracted by GPT from *container*."""


    props = {
        "listname": {
            "type": "string",
            "description": "Name of the listing"
        },
        "availability": {
            "type": "string",
            "description": "Availability of the listing. Return ONLY the **number** of available units"
        },
        "price_low": {
            "type": "string",
            "description": """
                Current price if there is a singular unit price 
                OR lower price in range if there is a unit price range
                only return if there is a numeric price value
                AND only return the **Integer** value of the price
            """
        },
        "price_high": {
            "type": "string",
            "description": """
                Upper price range ONLY IF there is a range,
                otherwise leave empty and fill price_low with price
            """
        },
        "pre_deal_price": {
            "type": "string",
            "description": """
                Price of the unit before any deals are applied, may have strikethrough on site
            """
        }
    }

    for key, value in filled.items():
        if value != None:
            props.pop(key, None)

    if not props:
        print("AI not necessary snapshots")
        return {}

    prompt = (
        "You are given an HTML snippet, representing a single floor-plan listing "
        "on a real-estate website. Parse the snippet and build "
        "a JSON object that follow the provided schema exactly. "
        "Return ONLY the list—no extra keys or wrapper.\n\n"
        f"{container}\n\n"
    )

    init_response = await asyncio.to_thread(
        client.beta.chat.completions.parse,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert web-scraping assistant"},
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "listing_snapshot",
                "schema": {
                    "description": "Data from a real estate listing snapshot",
                    "type": "object",
                    "properties": props
                }
            }
        }
    )

    raw_content = init_response.choices[0].message.content
    ai_listing_snapshot = json.loads(raw_content)


    try:
        listing_snapshot = ai_listing_snapshot.get("properties", {})
        if listing_snapshot:

            return listing_snapshot
        else:

            return ai_listing_snapshot
    except:
        print("AI could not find snapshot info")
        return {}


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



