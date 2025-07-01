from openai import OpenAI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import scrape_ai
from database import Database
from nav import Navigator
from match import Match
import normalize
import asyncio

load_dotenv()



async def main():
    db = Database()
    db.connect()

    # Limit the number of browsers that can be spawned at the same time
    semaphore = asyncio.Semaphore(5)

    sites = db.get_all_sites()
    await init_all_sites(sites, semaphore)

    floorplans = db.get_floorplan_urls()
    await scrape_all_fp(floorplans, semaphore)

    db.close()



async def init_all_sites(sites, sem):
    db = Database()
    db.connect()
    tasks = [init_site(site, sem) for site in sites if not db.previously_visited(site["id"])]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            print("init_site failed:", r)
    
async def init_site(site, sem):
    db = Database()
    db.connect()
    mat = Match()
    print("Initializing site: " + site["name"])
    async with sem:
        nav = Navigator()
        await nav.setup()
        await nav.get_page(site["url"])
        try:
            text = await nav.get_text()
            links = await nav.get_links()
            # print(links)
            link = mat.match_fp(site["url"], links)
            regex_filled = {}
            if link:
                print(link)
                regex_filled.update({"floorplans_url": link})
            
            ai_filled = await scrape_ai.ai_init(site["url"], text, regex_filled)
            site_data = {**ai_filled, **regex_filled}
        except Exception as e:
            print("init exception")
            print(e)
            return
        finally:
            await nav.close()
    print(site["name"])
    id = site["id"]
    print(site_data)
    db.insert_site(id, site_data)
    db.close()



async def scrape_all_fp(floorplans, sem):
    
    tasks = [scrape_fp(fp, sem) for fp in floorplans]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            print("task failed:", r)

async def scrape_fp(floorplan, sem):
    db = Database()
    db.connect()
    async with sem:
        nav = Navigator()
        await nav.setup()
        await nav.get_page(floorplan.url)

    selector = select(floorplan, nav, db)
    if selector == None:
        return
    
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
            listings = get_listings(floorplan, snippets)

            if listings:
                db.insert_listings(floorplan.site_id, listings)
                db.update_listing_count(floorplan.site_id, floorplan.property_id, count)
                print(f"Inserted {len(listings)} listings for site {floorplan.site_id}")
            else: 
                print(f"AI returned no listings for {floorplan.url}")
                
        snapshots = get_snapshots(floorplan, snippets)
        db.insert_listing_snapshots(floorplan.site_id, snapshots)
        print(f"Inserted {len(snapshots)} listing snapshots for site {floorplan.site_id}")
        
    except Exception as e:
        print(f"Error scraping listings for {floorplan.url}: {e}")
    finally:
        await nav.close()   
        db.close()



async def select(floorplan, nav: Navigator, db: Database):
    selector = db.get_selector(floorplan.site_id, floorplan.property_id)
    if not selector:
        # If not, use GPT to find a selector
        try:
            text = await nav.get_text()
            candidates = await scrape_ai.init_container(floorplan.url, text)
            # Get 3 candidates, ranked best first
        except Exception as e:
            print(f"Failed to get selector candidates for {floorplan.url}: {e}")
            await nav.close(); db.close(); return None

        # Try each candidate until one works
        chosen = None
        for cand in candidates:
            cand = scrape_ai.sanitize_selector(cand)
            try:
                # Check if the selector is valid
                await nav.page.wait_for_selector(cand, timeout=5000)
                elems = await nav.page.query_selector_all(cand)
                if 1 < len(elems) <= 50:
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
            await nav.close(); db.close(); return None

        # Save the selector to the DB
        selector = chosen
        db.save_selector(selector, floorplan.site_id, floorplan.property_id)
        print(f"Selector discovered and saved: {selector}")
        return selector



async def get_listings(floorplan, listing_text):
    mat = Match()
    listings = []
    
    for lt in listing_text:
        regex_listing = mat.match_listing(lt)
        ai_listing = scrape_ai.ai_parse_listings(lt, regex_listing)
        listing = {**ai_listing, **regex_listing}
        listings.append(listing)
    return listings

        
async def get_snapshots(floorplan, snapshot_text):
    mat = Match()
    snapshots = []

    for st in snapshot_text:
        regex_snapshot = mat.match_snapshot(st)
        ai_snapshot = scrape_ai.ai_parse_listing_snapshots(st, regex_snapshot)
        listing_snapshot = {**ai_snapshot, **regex_snapshot}
        snapshots.append(listing_snapshot)
    return snapshots

        
        

if __name__ == "__main__":
    asyncio.run(main())





