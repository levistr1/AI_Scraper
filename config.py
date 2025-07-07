regex_patterns = {
    "floorplan": r"/#?floor-?plans?/?",
    "bedrooms1": r"(?i)(studio|[1-9]{1})\s{1,3}(?:beds?|bd)",
    "bedrooms2": r"(?i)(?:beds?:?|bd:?)\s{1,3}(studio|[1-9]{1})",
    "bathrooms1": r"(?i)([1-9]{1})(?:\.[0-9]{1,2})?\s{1,3}(?:baths?|ba)",
    "bathrooms2": r"(?i)(?:baths?:?|ba:?)\s{1,3}([1-9]{1})(?:\.[0-9]{1,2})?",
    "sqft1": r"(?i)(\d+)\s{1,3}(?:sq.?\s*ft\.?\s*)",
    "sqft2": r"(?:sq.?\s*ft.?\s*:?)\s{1,3}(\d+)",
    "price": r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:[-–]|to\s*[-–]?)?\s*\$?\s*([\d,]+(?:\.\d{2})?)?",
    "availability1": r"(?i)(\d)\s*Available\s(units?)",
}

# Common successful floor plan container selector patterns
# These are examples of selectors that have worked well in practice
common_container_patterns = [
    # Class-based selectors
    "div.fp-card",
    "div.floorplan", 
    "div.floor-plan",
    "div.floorplan-card",
    "div.plan-card",
    "div.unit-card",
    "div.apartment-card",
    "div.listing-card",
    "article.floorplan",
    "section.floorplan",
    
    # ID-based patterns (for sites with dynamic IDs)
    "[id^='fp-']",
    "[id^='floorplan-']", 
    "[id^='plan-']",
    "[id^='unit-']",
    "[id^='eg-3-post-id']",
    "[id^='eg-post-']",
    "[id^='listing-']",
    
    # Data attribute patterns
    "[data-floorplan]",
    "[data-unit-type]",
    "[data-plan]",
    
    # Structure-based selectors
    ".floorplans-container > div",
    ".floor-plans-grid > div",
    ".units-list > div",
    ".apartments-grid > div",
    
    # Role-based selectors
    "[role='article']",
    "[itemtype*='Apartment']"
]

# Characteristics that indicate a good container element
container_characteristics = [
    "Contains bedroom/bathroom count",
    "Contains square footage",
    "Contains price or price range", 
    "Contains floor plan name/title",
    "Contains availability information",
    "Contains 'Apply Now' or similar action buttons",
    "Has consistent structure across multiple listings",
    "Wraps all related listing information together"
]