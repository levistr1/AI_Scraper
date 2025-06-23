import mysql.connector
from typing import TypedDict, Optional, List
from scrape_ai import ContainerSelector
from scrape_ai import Site

class FPRecord(TypedDict):
    site_id: int
    property_id: Optional[int]   # None when URL belongs to the site itself
    url: str

# ---------------------------------------------------------------------------
#  Simple container for floor-plan URLs
# ---------------------------------------------------------------------------

class FloorplanURL:
    """Holds the mapping between a floor-plan page and its owner rows."""

    def __init__(self, site_id: int, url: str, property_id: Optional[int] = None):
        self.site_id: int = site_id
        self.property_id: Optional[int] = property_id
        self.url: str = url

    # Helpful for debugging / logging
    def __repr__(self) -> str:  # pragma: no cover – utility only
        return (
            f"FloorplanURL(site_id={self.site_id}, "
            f"property_id={self.property_id}, url={self.url!r})"
        )

class Database:

    def __init__(self):
        self.connection = None
        # cache of floor-plan URLs built by get_floorplan_urls()
        self.fps: list[FloorplanURL] = []

    def connect(self):
        self.connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Summer2025!",
            database="real_estate_ai")
        
    def close(self):
        self.connection.close()

    def get_all_sites(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, url, floorplans_url FROM site")
        return cursor.fetchall()
    
    def get_all_listings(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM listings")
        return cursor.fetchall()

    
    
    def insert_properties(self, site_id: int, site: Site):
        cursor = self.connection.cursor()

        sql = (
            "INSERT INTO property "
            "(site_id, floorplans_url, title, amenities, address) "
            "VALUES (%s, %s, %s, %s, %s)"
        )

        data = [
            (
                site_id,
                prop.floorplans_url,
                prop.title,
                prop.amenities,
                prop.address,
            )
            for prop in site.properties
        ]

        cursor.executemany(sql, data)   # one round-trip for all rows
        self.connection.commit()

    
    def insert_site(self, site_id: int, site: Site):
        cursor = self.connection.cursor()

        # 1) Update floor-plans URL if provided.
        if site.floorplans_url:
            cursor.execute(
                "UPDATE site SET floorplans_url = %s WHERE id = %s",
                (site.floorplans_url, site_id),
            )

        # 2) Update descriptive fields (skip NULLs so we don't overwrite).
        cursor.execute(
            "UPDATE site SET address = COALESCE(%s,address), "
            "state = COALESCE(%s,state), amenities = COALESCE(%s,amenities), "
            "deals = COALESCE(%s,deals) WHERE id = %s",
            (site.address, site.state, site.amenities, site.deals, site_id),
        )

        # 3) If there are child properties, ensure they exist in the DB.
        if site.properties:
            self.insert_properties(site_id, site)

        self.connection.commit()

    def get_floorplan_urls(self):
        """Return a list of mappings with the URL and its owning site / property.

        Each element has the form::

            {
                "site_id":      <int>,            # always present
                "property_id":  <int | None>,     # None when url belongs to site
                "url":          <str>,
            }

        This makes it easy to know where to write data back after scraping.
        """

        cursor = self.connection.cursor(dictionary=True)
        
        # Clear previous cache so repeated calls return fresh data
        self.fps = []

        for site in self.get_all_sites():
            site_id = site["id"]

            # 1. Site-level floor-plans URL?
            if site["floorplans_url"]:
                self.fps.append(FloorplanURL(site_id, site["floorplans_url"]))
                continue  # skip property iteration for this site

            # 2. Otherwise gather property-level URLs.
            cursor.execute(
                "SELECT id, floorplans_url FROM property WHERE site_id = %s AND floorplans_url IS NOT NULL",
                (site_id,),
            )
            for row in cursor.fetchall():
                self.fps.append(FloorplanURL(site_id, row["floorplans_url"], row["id"]))

        return self.fps


