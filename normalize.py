class Normalizer:
    def __init__(self):
        pass
    
    def normalize_price(self, price) -> int:
        p = int(float(price.replace(",","").replace("$", "")))
        return p
    
    def normalize_sqft(self, sqft) -> int:
        sq = int(sqft.replace(",",""))
        return sq
            
    def normalize_price_range(self, low, high) -> bool:
        if low is not None:
            low = self.normalize_price(low)
        if high is not None:
            high = self.normalize_price(high)
        
        if low is not None:
            if high is not None:
                if high < low: 
                    return False
                else:
                    return True
            else:  
                return True
        else:
            return False
                    
        

