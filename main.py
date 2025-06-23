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
    await init_all_fp(floorplans)



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




async def init_fp(floorplan):
    db = Database()
    db.connect()
    nav = Navigator()
    await nav.setup()
    await nav.get_page(floorplan.url)
    try:
        text = await nav.get_text()
        container_selector = await scrape_ai.init_container(floorplan.url, text)
        print(container_selector)
    except Exception as e:
        print(e)
    finally:
        await nav.close()
    db.close()
    


async def init_all_fp(floorplans):
    tasks = [init_fp(floorplan) for floorplan in floorplans]
    await asyncio.gather(*tasks)
    

    
def scrape_all(sites):
    for site in sites:
        url = site["url"]
        site_id = site["id"]
        name = site["name"]
        



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

def scrape_site(site_id: int):
    return 0

def find_floorplans(site_id: int):
    return 0



if __name__ == "__main__":
    asyncio.run(main())





