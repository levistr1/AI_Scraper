class Normalizer:
    def __init__(self):
        pass
    
    def normalize_price(self, price) -> int:
        norm_prices = []
        for p in price:
            if p != None:
                
                p = int(float(p.replace(",","")))
                norm_prices.append(p)
        if len(norm_prices) > 1 and norm_prices[0] == norm_prices[1]:
            norm_prices.pop()
        return norm_prices
            
        

