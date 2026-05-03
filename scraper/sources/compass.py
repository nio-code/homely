"""
Compass scraper.
Compass emits paired JSON-LD blocks per listing card:
  1. SingleFamilyResidence — address, geo, url
  2. Product             — price (in offers), url (same)
We join them on URL, then parse HTML cards for beds/baths/sqft/agent.
"""
import json
import re
from typing import Dict, List, Optional

from ..models import Listing
from .base import BaseScraper


class CompassScraper(BaseScraper):
    source_name = "compass"
    page_size = 20

    def search_url(self, zip_code: str, page: int) -> str:
        # The type/house filter path redirects; use the base search with zip query
        return (
            f"https://www.compass.com/homes-for-sale/irvine-ca/"
            f"?zipCode={zip_code}&page={page}"
        )

    def parse_search_page(self, html: str, zip_code: str) -> List[Listing]:
        listings = []

        # ── Step 1: collect all JSON-LD blocks, keyed by URL ──────────────────
        addr_by_url: Dict[str, dict] = {}   # url → SingleFamilyResidence block
        price_by_url: Dict[str, int] = {}    # url → price int

        for ld in self.extract_json_ld(html):
            t = ld.get("@type", "")
            url = ld.get("url", "")
            if not url:
                continue
            if t in ("SingleFamilyResidence", "House", "RealEstateListing"):
                addr_by_url[url] = ld
            elif t == "Product":
                offers = ld.get("offers", {})
                p = self.parse_price(str(offers.get("price", 0))) or 0
                if p:
                    price_by_url[url] = p

        # ── Step 2: merge pairs ───────────────────────────────────────────────
        for url, ld in addr_by_url.items():
            price = price_by_url.get(url, 0)
            l = self._from_ld_pair(ld, price, zip_code)
            if l:
                listings.append(l)

        # ── Step 3: fallback — HTML card scraping ─────────────────────────────
        if not listings:
            soup = self.soup(html)
            cards = soup.select(
                "[data-tn='listing-card'], .uc-listingCard, "
                ".listingCard-container, [data-testid='listing-card']"
            )
            for card in cards:
                l = self._from_card(card, zip_code)
                if l:
                    listings.append(l)

        return listings

    def _from_ld_pair(self, ld: dict, price: int, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            addr = ld.get("address", {})
            l.zip_code = addr.get("postalCode", zip_code)
            l.address = addr.get("streetAddress", "")
            l.city = addr.get("addressLocality", "Irvine")
            l.state = addr.get("addressRegion", "CA")
            l.listing_url = ld.get("url", "")
            l.price = price
            l.property_type = "sfr"

            # source_id from URL path  e.g. /homedetails/…/1KKTVO_pid/
            m = re.search(r"/([A-Z0-9_]{6,})_pid", l.listing_url)
            l.source_id = m.group(1) if m else ""

            # beds/baths/sqft are NOT in JSON-LD — will be null; scraper marks garage unknown
            l.beds = 0.0
            l.baths = 0.0
            l.sqft = None
            l.has_garage = False

            # Agent: Compass rarely exposes agent in JSON-LD search cards;
            # the individual listing page has it — left blank here for batch scrape.

            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None

    def _from_card(self, card, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            l.zip_code = zip_code
            l.property_type = "sfr"

            price_el = card.select_one(
                "[data-tn='listing-card-price'], .listingCard-price, .price"
            )
            l.price = self.parse_price(price_el.get_text()) if price_el else 0

            addr_el = card.select_one(
                "[data-tn='listing-card-address'], .listingCard-address, address"
            )
            l.address = addr_el.get_text(strip=True) if addr_el else ""

            link = card.select_one("a[href]")
            href = link["href"] if link else ""
            l.listing_url = href if href.startswith("http") else f"https://www.compass.com{href}"

            m = re.search(r"/([A-Z0-9_]{6,})_pid", l.listing_url)
            l.source_id = m.group(1) if m else ""

            text = card.get_text(" ", strip=True)
            beds, baths = self.parse_beds_baths(text)
            l.beds = beds or 0.0
            l.baths = baths or 0.0

            sqft_m = re.search(r"([\d,]+)\s*sq\s*ft", text, re.I)
            l.sqft = int(sqft_m.group(1).replace(",", "")) if sqft_m else None

            l.has_garage, l.garage_spaces = self.detect_garage(text)
            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None
