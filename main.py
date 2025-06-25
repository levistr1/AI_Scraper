from openai import OpenAI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import scrape_ai
from database import Database
from nav import Navigator
import normalize
import asyncio

load_dotenv()



async def main():
    db = Database()
    db.connect()

    sites = db.get_all_sites()
    await init_all_sites(sites)

    floorplans = db.get_floorplan_urls()
    await scrape_all_fp(floorplans)

    db.close()



async def init_all_sites(sites):
    tasks = [init_site(site) for site in sites if not previously_visited(site["id"])]
    await asyncio.gather(*tasks)
    
async def init_site(site):
    db = Database()
    db.connect()
    print("Initializing site: " + site["name"])
    nav = Navigator()
    await nav.setup()
    await nav.get_page(site["url"])
    try:
        text = await nav.get_text()
        site_obj = await scrape_ai.ai_init(site["url"], text)
    except Exception as e:
        print(e)
        return
    finally:
        await nav.close()
    print(site["name"])
    id = site["id"]
    print(site_obj)
    db.insert_site(id, site_obj)
    db.close()



async def scrape_all_fp(floorplans):
    
    tasks = [scrape_fp(fp) for fp in floorplans]
    await asyncio.gather(*tasks)

async def scrape_fp(floorplan):
    db = Database()
    db.connect()
    nav = Navigator()
    await nav.setup()
    await nav.get_page(floorplan.url)

    # Check to see if we have a selector saved in DB
    selector = db.get_selector(floorplan.site_id, floorplan.property_id)
    if not selector:
        # If not, use GPT to find a selector
        try:
            text = await nav.get_text()
            candidates = await scrape_ai.init_container(floorplan.url, text)
            # Get 3 candidates, ranked best first
        except Exception as e:
            print(f"Failed to get selector candidates for {floorplan.url}: {e}")
            await nav.close(); db.close(); return

        # Try each candidate until one works
        chosen = None
        for cand in candidates:
            cand = scrape_ai.sanitize_selector(cand)
            try:
                # Check if the selector is valid
                await nav.page.wait_for_selector(cand, timeout=5000)
                elems = await nav.page.query_selector_all(cand)
                if 0 < len(elems) <= 100:
                    chosen = cand
                    break
            except Exception:
                continue

        if not chosen:
            # Try heuristic based on repeating id prefix
            heuristic = await scrape_ai.heuristic_id_prefix_selector(nav.page)
            if heuristic:
                try:
                    await nav.page.wait_for_selector(heuristic, timeout=5000)
                    elems = await nav.page.query_selector_all(heuristic)
                    if 0 < len(elems) <= 100:
                        chosen = heuristic
                except Exception:
                    pass

        if not chosen:
            print(f"No valid selector found for {floorplan.url}")
            await nav.close(); db.close(); return

        # Save the selector to the DB
        selector = chosen
        db.save_selector(selector, floorplan.site_id, floorplan.property_id)
        print(f"Selector discovered and saved: {selector}")
    
    # Number of listings on page with that selector 
    count = await nav.page.locator(selector).count()
    # Number of listings in DB with that selector
    prev_count = db.get_listing_count(floorplan.site_id, floorplan.property_id)

    
    try:
        # Get text from inside all listing containers
        await nav.page.wait_for_selector(selector)
        elements = await nav.page.query_selector_all(selector)
        snippets = [await el.inner_html() for el in elements]

        if not snippets:
            print(f"No listing containers found for {floorplan.url} with selector {selector}")
            return
        if prev_count is None or prev_count != count:
            listings = await scrape_ai.ai_parse_listings(floorplan.url, snippets)
            if listings:
                db.insert_listings(floorplan.site_id, floorplan.property_id, listings)
                db.update_listing_count(floorplan.site_id, floorplan.property_id, count)
                print(f"Inserted {len(listings)} listings for site {floorplan.site_id}")
            else: 
                print(f"AI returned no listings for {floorplan.url}")
                
        listing_snapshots = await scrape_ai.ai_parse_listing_snapshots(floorplan.url, snippets)
        db.insert_listing_snapshots(floorplan.site_id, floorplan.property_id, listing_snapshots)
        print(f"Inserted {len(listing_snapshots)} listing snapshots for site {floorplan.site_id}")
        
    except Exception as e:
        print(f"Error scraping listings for {floorplan.url}: {e}")
    finally:
        await nav.close()
        db.close()





def previously_visited(site_id: int):
    db = Database()
    db.connect()
    cursor = db.connection.cursor(dictionary=True)
    cursor.execute("SELECT id from property where site_id = %s", (site_id,))
    property = cursor.fetchone()
    cursor.execute("SELECT floorplans_url from site where id = %s", (site_id,))
    floorplans_url = cursor.fetchone()
    if property is None and floorplans_url['floorplans_url'] is None:
        return False
    else:
        return True



if __name__ == "__main__":
    asyncio.run(main())





