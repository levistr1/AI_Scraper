import mysql.connector
from typing import TypedDict, Optional, List
from scrape_ai import SelectorList
from scrape_ai import Site
from scrape_ai import Listing
from scrape_ai import ListingSnapshot
from normalize import Normalizer

class FPRecord(TypedDict):
    site_id: int
    property_id: Optional[int]   # None when URL belongs to the site itself
    url: str

# ---------------------------------------------------------------------------
#  Simple container for floor-plan URLs
# ---------------------------------------------------------------------------
norm = Normalizer()

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

    # --------------------------------------------------------------
    # Connection
    # --------------------------------------------------------------

    def __init__(self):
        self.connection = None
        # cache of floor-plan URLs built by get_floorplan_urls()
        self.fps: list[FloorplanURL] = []

    def connect(self):
        self.connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Summer2025!",
            database="real_estate_ai",
            autocommit=True,
        )
        
    def close(self):
        self.connection.close()
    
    # --------------------------------------------------------------
    # Insert / Update 
    # --------------------------------------------------------------
        
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

    def insert_listings(
        self,
        site_id: int,
        property_id: Optional[int],
        listings: List[Listing],
    ) -> None:
        """Bulk-insert Listing rows, skip duplicates via INSERT IGNORE."""

        cursor = self.connection.cursor()
        sql = (
            "INSERT IGNORE INTO listing "
            "(site_id, property_id, listname, bedrooms, bathrooms, sqft, shared_room, amenities) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
        )

        data = [
            (
                site_id,
                property_id,
                l.listname,
                l.bedrooms,
                l.bathrooms,
                l.sqft,
                int(l.shared_room) if l.shared_room is not None else None,
                l.amenities,

            )
            for l in listings
        ]

        cursor.executemany(sql, data)
        self.connection.commit()

    def insert_listing_snapshots(self, site_id: int, property_id: Optional[int], snaps: List[ListingSnapshot]):
        cursor = self.connection.cursor()
        sql = (
            "INSERT INTO listing_snapshot "
            "(listing_id, availability, price, pre_deal_price, deals)"
            "VALUES (%s,%s,%s,%s,%s)"
        )

        data = []
        for s in snaps:
            listing_id = self.lookup_listing_id(site_id, property_id, s.listname)
            if listing_id is None:
                continue  # listing not yet in table
            data.append((listing_id, s.availability, norm.normalize_price(s.price), s.pre_deal_price, s.deals))

        if data:
            cursor.executemany(sql, data)
            self.connection.commit()

    def save_selector(self, selector: str, site_id: int, property_id: Optional[int] = None):
        """Persist the *selector* into the correct table row."""

        cursor = self.connection.cursor()
        if property_id is None:
            cursor.execute(
                "UPDATE site SET container_selector = %s WHERE id = %s",
                (selector, site_id),
            )
        else:
            cursor.execute(
                "UPDATE property SET container_selector = %s WHERE id = %s",
                (selector, property_id),
            )
        self.connection.commit()

    def update_listing_count(self, site_id: int, property_id: Optional[int], count: int):
        cursor = self.connection.cursor()
        if property_id is None:
            cursor.execute("UPDATE site SET listing_count = %s WHERE id = %s", (count, site_id,))
        else:
            cursor.execute("UPDATE property SET listing_count = %s WHERE id = %s", (count, property_id,))
        self.connection.commit()

    # --------------------------------------------------------------
    # Get / Lookup
    # --------------------------------------------------------------

    def get_all_sites(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, url, floorplans_url FROM site")
        return cursor.fetchall()
    
    def get_all_listings(self):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM listings")
        return cursor.fetchall()

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

    def get_selector(self, site_id: int, property_id: Optional[int] = None) -> Optional[str]:
        """Return the stored container selector or ``None`` if absent."""

        cursor = self.connection.cursor()
        if property_id is None:
            cursor.execute("SELECT container_selector FROM site WHERE id = %s", (site_id,))
        else:
            cursor.execute("SELECT container_selector FROM property WHERE id = %s", (property_id,))

        res = cursor.fetchone()
        if not res:
            return None
        return res[0]

    def get_listing_count(self, site_id: int, property_id: Optional[int] = None) -> int:
        cursor = self.connection.cursor()
        if property_id is None:
            cursor.execute("SELECT listing_count FROM site WHERE id = %s", (site_id,))
        else:
            cursor.execute("SELECT listing_count FROM property WHERE id = %s", (property_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def lookup_listing_id(self, site_id: int, property_id: Optional[int], listname: str) -> Optional[int]:
        cursor = self.connection.cursor()
        if property_id is None:
            cursor.execute(
                "SELECT id FROM listing WHERE site_id = %s AND property_id IS NULL AND listname = %s",
                (site_id, listname),
            )
        else:
            cursor.execute(
                "SELECT id FROM listing WHERE site_id = %s AND property_id = %s AND listname = %s",
                (site_id, property_id, listname),
            )
        row = cursor.fetchone()
        return row[0] if row else None


    def previously_visited(self, site_id: int):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT id from property where site_id = %s", (site_id,))
        property = cursor.fetchone()
        junk = cursor.fetchall()
        cursor.execute("SELECT floorplans_url from site where id = %s", (site_id,))
        floorplans_url = cursor.fetchone()
        junk2 = cursor.fetchall()
        if property is None and floorplans_url['floorplans_url'] is None:
            return False
        else:
            return True
