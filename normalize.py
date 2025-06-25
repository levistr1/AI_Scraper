class Normalizer:
    def __init__(self):
        pass
    
    def normalize_price(self, price: str) -> str:
        price = price.strip().replace("–", "-").split("-")
        if len(price) == 1:
            return price[0].strip().replace("$", "").replace(",", "")
        else:
            return price[0].strip().replace("$", "").replace(",", "") + " - " + price[1].strip().replace("$", "").replace(",", "")

