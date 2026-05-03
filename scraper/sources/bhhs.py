"""Berkshire Hathaway HomeServices California Properties scraper."""
import re
from typing import List, Optional

from ..models import Listing
from .base import BaseScraper


class BHHSScraper(BaseScraper):
    source_name = "bhhs"
    page_size = 24

    def search_url(self, zip_code: str, page: int) -> str:
        return (
            f"https://www.bhhscalifornia.com/homes-for-sale/"
            f"?zipCode={zip_code}&propType=SFR&beds_min=3&baths_min=2&sqft_min=1000"
            f"&page={page}"
        )

    def parse_search_page(self, html: str, zip_code: str) -> List[Listing]:
        listings = []
        for ld in self.extract_json_ld(html):
            if ld.get("@type") in ("RealEstateListing", "House"):
                l = self._from_json_ld(ld, zip_code)
                if l:
                    listings.append(l)

        if not listings:
            soup = self.soup(html)
            cards = soup.select(".property-card, .listing-card, [data-property-id]")
            for card in cards:
                l = self._from_card(card, zip_code)
                if l:
                    listings.append(l)

        return listings

    def _from_json_ld(self, ld: dict, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            addr = ld.get("address", {})
            l.zip_code = addr.get("postalCode", zip_code)
            l.address = addr.get("streetAddress", "")
            l.city = addr.get("addressLocality", "Irvine")
            l.price = self.parse_price(str(ld.get("offers", {}).get("price", 0))) or 0
            l.property_type = "sfr"
            l.listing_url = ld.get("url", "")
            desc = ld.get("description", "")
            beds, baths = self.parse_beds_baths(desc)
            l.beds = beds or 0
            l.baths = baths or 0
            l.has_garage, l.garage_spaces = self.detect_garage(desc)
            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None

    def _from_card(self, card, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            l.zip_code = zip_code
            l.property_type = "sfr"
            text = card.get_text(" ", strip=True)
            price_m = re.search(r"\$([\d,]+)", text)
            l.price = int(price_m.group(1).replace(",", "")) if price_m else 0
            addr_el = card.select_one(".property-address, address")
            l.address = addr_el.get_text(strip=True) if addr_el else ""
            link = card.select_one("a[href]")
            href = link["href"] if link else ""
            l.listing_url = href if href.startswith("http") else f"https://www.bhhscalifornia.com{href}"
            beds, baths = self.parse_beds_baths(text)
            l.beds = beds or 0
            l.baths = baths or 0
            sqft_m = re.search(r"([\d,]+)\s*sq", text, re.I)
            l.sqft = int(sqft_m.group(1).replace(",", "")) if sqft_m else None
            l.has_garage, l.garage_spaces = self.detect_garage(text)
            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None
