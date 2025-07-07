class Normalizer:
    def __init__(self):
        pass
    
    def normalize_price(self, price) -> int:
        p = int(float(price.replace(",","").replace("$", "")))
        return p
            
        

