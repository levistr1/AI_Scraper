import re
from config import regex_patterns
from normalize import Normalizer

norm = Normalizer()

text = """

"""
prices = [
    "$1,695to-$1,760",
    "$1,950",
    "$1,816 - $2,720",
    "$1749",
    "$2720 – $2720",
    "$1,425to-$1,513",
    "$1329.00",
    "$1,530-$1,755",
    "$ 1,335",
]
# Replace HTML non-breaking spaces with real unicode non-breaking space
text = text.replace("&nbsp;", "\u00A0")
pattern = re.compile(regex_patterns["price"])
for price in prices:
    match = pattern.search(price)
    if match:
        m = norm.normalize_price(match.groups())
        print(m)



matches = pattern.findall(text)
for match in matches:
    print("MATCH:", match)

# print(f"total: {total} matched: {worked}")

