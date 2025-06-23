from openai import OpenAI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import scrape_ai
from database import Database
from nav import Navigator
import asyncio

load_dotenv()



async def main():
    db = Database()
    db.connect()

    sites = db.get_all_sites()
    await init_all_sites(sites)

    floorplans = db.get_floorplan_urls() # only this db has valid fps obj
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

    # 1. Ensure we have a container selector saved in DB
    selector = db.get_selector(floorplan.site_id, floorplan.property_id)
    if not selector:
        try:
            text = await nav.get_text()
            selector = await scrape_ai.init_container(floorplan.url, text)
            db.save_selector(selector, floorplan.site_id, floorplan.property_id)
            print(f"Selector discovered and saved: {selector}")
        except Exception as e:
            print(f"Failed to discover selector for {floorplan.url}: {e}")
            await nav.close()
            db.close()
            return

    # 2. Use selector to extract listing containers and parse them
    try:
        await nav.page.wait_for_selector(selector)
        elements = await nav.page.query_selector_all(selector)
        snippets = [await el.inner_html() for el in elements]

        if not snippets:
            print(f"No listing containers found for {floorplan.url} with selector {selector}")
            return

        listings = await scrape_ai.ai_parse_listings(floorplan.url, snippets)
        if listings:
            db.insert_listings(floorplan.site_id, floorplan.property_id, listings)
            print(f"Inserted {len(listings)} listings for site {floorplan.site_id}")
        else:
            print(f"AI returned no listings for {floorplan.url}")
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





