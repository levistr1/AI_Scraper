import re
from config import regex_patterns
from normalize import Normalizer

norm = Normalizer()

text = """
     <div class="esg-media-cover-wrapper">
<div class="esg-entry-media-wrapper esg-entry-media-wrapper-not-even"><div class="esg-entry-media" style="padding-bottom: 100%;"><img loading="lazy" decoding="async" class="esg-entry-media-img" src="https://hooverandgreene.com/wp-content/uploads/2025/07/HOO-S1.jpg" data-no-lazy="1" alt="0 bedroom apartment for rent" width="1000" height="1000" style="display: none;"><div class="esg-media-poster" src="https://hooverandgreene.com/wp-content/uploads/2025/07/HOO-S1.jpg" data-src="https://hooverandgreene.com/wp-content/uploads/2025/07/HOO-S1.jpg" data-lazythumb="undefined" style="background-image: url(&quot;https://hooverandgreene.com/wp-content/uploads/2025/07/HOO-S1.jpg&quot;); opacity: 1; visibility: inherit; transform: translate3d(0px, 0px, 0px);"></div></div></div>

            <div class="esg-entry-cover" style="height: 267px;">

                <div class="esg-overlay esg-transition eg-vio-floorplan-skin-container" data-transition="esg-none" style="transform: translate(0px, 0px); opacity: 1; visibility: inherit;"></div>

                                <div class="esg-cc eec" style="top: 105px;"><div class="esg-center eg-post-15011 eg-vio-floorplan-skin-element-34 esg-transition" data-delay="0.09" data-duration="default" data-transition="esg-skewright" style="transform-origin: 50% 50%; opacity: 0; visibility: hidden; transform: translate(-100%, 0%) skew(60deg, 0deg);"><p>Available Units</p></div><div class="esg-center eg-vio-floorplan-skin-element-2 esg-none esg-clear esg-line-break"></div><div class="esg-center eg-post-15011 eg-vio-floorplan-skin-element-4 esg-transition" data-delay="0.09" data-duration="default" data-transition="esg-skewright" style="transform-origin: 50% 50%; opacity: 0; visibility: hidden; transform: translate(-100%, 0%) skew(60deg, 0deg);">2</div><div></div></div>
              

           </div>
<div class="esg-entry-content eg-vio-floorplan-skin-content esg-notalone" style="min-height: 0px;">
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-1-a"><a class="eg-vio-floorplan-skin-element-1 eg-post-15011" href="https://hooverandgreene.com/s1-apartment/" target="_self">S1 Apartment</a></div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-29"><i class="fa-icon-hotel"></i></div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-25">Studio Beds</div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-30"><i class="fa-icon-bathtub"></i></div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-3">1 Baths</div>
              <div class="esg-content eg-vio-floorplan-skin-element-6 esg-none esg-clear esg-line-break"></div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-7"><p>anemptytextlline</p></div>
              <div class="esg-content eg-vio-floorplan-skin-element-8 esg-none esg-clear esg-line-break"></div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-32-a"><a class="eg-vio-floorplan-skin-element-32 eg-post-15011" data-thumb="https://hooverandgreene.com/wp-content/uploads/2025/07/HOO-S1-200x200.jpg" href="javascript:void(0);"><i class="fa-icon-cube"></i></a></div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-9">498 sq ft</div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-26">$2245 – $2245</div>
              <div class="esg-content eg-vio-floorplan-skin-element-10 esg-none esg-clear esg-line-break"></div>
                                <div class="esg-content eg-post-15011 eg-vio-floorplan-skin-element-11-a"><a class="eg-vio-floorplan-skin-element-11 eg-post-15011" href="https://hooverandgreene.com/s1-apartment/" target="_self"><p>Apply Now</p></a></div>
</div>   </div>
"""

# Replace HTML non-breaking spaces with real unicode non-breaking space
text = text.replace("&nbsp;", "\u00A0")

beds_pattern1 = re.compile(regex_patterns["bedrooms1"])
beds_pattern2 = re.compile(regex_patterns["bedrooms2"])
baths_pattern1 = re.compile(regex_patterns["bathrooms1"])
baths_pattern2 = re.compile(regex_patterns["bathrooms2"])
sqft_pattern1 = re.compile(regex_patterns["sqft1"])
sqft_pattern2 = re.compile(regex_patterns["sqft2"])
price_pattern = re.compile(regex_patterns["price"])

t_beds = beds_pattern1.search(text)
if t_beds:
    t_baths = baths_pattern1.search(text, t_beds.end())
else:
    t_beds = beds_pattern2.search(text)
    t_baths = baths_pattern2.search(text)

    
t_sqft = sqft_pattern1.search(text)
if not t_sqft:
    t_sqft = sqft_pattern2.search(text)

    
t_price = price_pattern.search(text)

beds = t_beds.group(1) if t_beds else None
baths = t_baths.group(1) if t_baths else None
sqft = t_sqft.group(1) if t_sqft else None
price = t_price.groups() if t_price else None

print(beds)
print(baths)
print(sqft)
print(price)


