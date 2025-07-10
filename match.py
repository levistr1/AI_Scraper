from config import regex_patterns
import re
from normalize import Normalizer

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

        beds_pattern1 = re.compile(regex_patterns["bedrooms1"])
        beds_pattern2 = re.compile(regex_patterns["bedrooms2"])
        baths_pattern1 = re.compile(regex_patterns["bathrooms1"])
        baths_pattern2 = re.compile(regex_patterns["bathrooms2"])
        sqft_pattern1 = re.compile(regex_patterns["sqft1"])
        sqft_pattern2 = re.compile(regex_patterns["sqft2"])

        t_beds = beds_pattern1.search(text)
        if t_beds:
            t_baths = baths_pattern1.search(text, t_beds.end())
        else:
            t_beds = beds_pattern2.search(text)
            t_baths = baths_pattern2.search(text)
        
        t_sqft = sqft_pattern1.search(text)
        if not t_sqft:
            t_sqft = sqft_pattern2.search(text)


        beds = t_beds.group(1) if t_beds else None
        baths = t_baths.group(1) if t_baths else None
        sqft = t_sqft.group(1) if t_sqft else None

        if beds and beds.lower() == "studio":
            beds = 0
    
        listing = {
            "bedrooms": beds,
            "bathrooms": baths,
            "sqft": sqft
        }


        return listing
    
    def match_snapshot(self, text: str) -> dict:
        norm = Normalizer()
        price_pattern = re.compile(regex_patterns["price"])
        availability_pattern = re.compile(regex_patterns["availability1"])

        t_price = price_pattern.search(text)
        t_availability = availability_pattern.search(text)

        prices = t_price.groups() if t_price else None
        if prices:
            if len(prices) > 1:
                low = prices[0]
                high = prices[1]
            else:
                low = prices[0]
                high = None
        else:
            low = None
            high = None

        if not norm.normalize_price_range(low, high):
            low = None
            high = None
        
        availability = t_availability.group(1) if t_availability else None

        listing_snapshot = {
            "price_low": low,
            "price_high": high,
            "availability": availability
        }

        return listing_snapshot



        
    
        

