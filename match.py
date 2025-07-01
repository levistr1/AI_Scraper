from config import regex_patterns
import re

class Match:
    def __init__(self):
        pass

    def match_fp(self, url: str, links) -> str:
        pattern = re.compile(regex_patterns["floorplan"])
        for link in links:
            l = link["href"]
            if l:
                match = pattern.search(l)
                if match:
                    if l.startswith("http"):
                        return l
                    elif url.endswith("/"):
                        return url + l[1:]
                    else:
                        return url + l
        return None
    

    def match_listing(self, text: str) -> dict:
        text = text.replace("&nbsp;", "\u00A0")

        beds_pattern = re.compile(regex_patterns["bedrooms"])
        baths_pattern = re.compile(regex_patterns["bathrooms"])
        sqft_pattern = re.compile(regex_patterns["sqft"])

        t_beds = beds_pattern.search(text)
        if t_beds:
            t_baths = baths_pattern.search(text, t_beds.end())
        t_sqft = sqft_pattern.search(text)

        beds = t_beds.group(1) if t_beds else None
        baths = t_baths.group(1) if t_baths else None
        sqft = t_sqft.group(1) if t_sqft else None

        if beds.lower() == "studio":
            beds = 0
    
        listing = {
            "bedrooms": beds,
            "bathrooms": baths,
            "sqft": sqft
        }

        return listing
    
    def match_snapshot(self, text: str) -> dict:
        price_pattern = re.compile(regex_patterns["price"])
        availability_pattern = re.compile(regex_patterns["availability"])

        t_price = price_pattern.search(text)
        t_availability = availability_pattern.search(text)

        price = t_price.group(1)
        availability = t_availability.group(1)

        listing_snapshot = {
            "price": price,
            "availability": availability
        }

        return listing_snapshot



        
    
        

