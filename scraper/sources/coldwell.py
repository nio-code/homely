"""
Coldwell Banker Homes scraper.
Search URL: https://www.coldwellbankerhomes.com/ca/irvine/?propType=SFR&beds=3-&baths=2-&sqft=1000-&zip=XXXXX
Listings are rendered as JSON-LD + data attributes in the search results grid.
"""
import re
from typing import List, Optional

from ..models import Listing
from .base import BaseScraper


class ColdwellBankerScraper(BaseScraper):
    source_name = "coldwell_banker"
    page_size = 36

    def search_url(self, zip_code: str, page: int) -> str:
        offset = (page - 1) * self.page_size
        return (
            f"https://www.coldwellbankerhomes.com/search/"
            f"?zipCode={zip_code}"
            f"&propType=SFR"
            f"&beds_min=3"
            f"&baths_min=2"
            f"&sqft_min=1000"
            f"&start={offset}"
            f"&pageSize={self.page_size}"
        )

    def parse_search_page(self, html: str, zip_code: str) -> List[Listing]:
        listings = []

        # Strategy 1: JSON-LD RealEstateListing blocks
        for ld in self.extract_json_ld(html):
            if ld.get("@type") in ("RealEstateListing", "SingleFamilyResidence"):
                l = self._from_json_ld(ld, zip_code)
                if l:
                    listings.append(l)

        # Strategy 2: HTML listing cards
        if not listings:
            soup = self.soup(html)
            cards = soup.select(".property-card, .listing-card, [data-listing-id], .MLS-listing")
            for card in cards:
                l = self._from_card(card, zip_code)
                if l:
                    listings.append(l)

        # Strategy 3: embedded JS data object
        if not listings:
            data = self.extract_embedded_json(html, "cbPropertySearchData")
            if data and "listings" in data:
                for item in data["listings"]:
                    l = self._from_dict(item, zip_code)
                    if l:
                        listings.append(l)

        return listings

    def _from_json_ld(self, ld: dict, zip_code: str) -> Optional[Listing]:
        try:
            addr = ld.get("address", {})
            price_data = ld.get("offers", {})
            l = Listing()
            l.zip_code = addr.get("postalCode", zip_code)
            l.address = addr.get("streetAddress", "")
            l.city = addr.get("addressLocality", "Irvine")
            l.state = addr.get("addressRegion", "CA")
            l.listing_url = ld.get("url", "")
            l.price = self.parse_price(str(price_data.get("price", 0))) or 0
            l.property_type = "sfr"
            l.agent_name = (ld.get("agent") or {}).get("name")
            l.agent_phone = self.clean_phone((ld.get("agent") or {}).get("telephone"))

            desc = ld.get("description", "")
            beds, baths = self.parse_beds_baths(desc)
            l.beds = beds or 0
            l.baths = baths or 0
            l.has_garage, l.garage_spaces = self.detect_garage(desc)
            l.fingerprint = self.fingerprint_listing(l.address, l.price)

            # MLS / source_id
            l.source_id = ld.get("identifier", {}).get("value", "") or ld.get("@id", "")

            return l if l.address and l.price > 0 else None
        except Exception:
            return None

    def _from_card(self, card, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            l.zip_code = zip_code

            price_el = card.select_one(".price, .listing-price, [data-price]")
            l.price = self.parse_price(price_el.get_text()) if price_el else 0

            addr_el = card.select_one(".address, .listing-address, [data-address]")
            l.address = addr_el.get_text(strip=True) if addr_el else ""

            link = card.select_one("a[href]")
            l.listing_url = link["href"] if link else ""
            if l.listing_url and not l.listing_url.startswith("http"):
                l.listing_url = "https://www.coldwellbankerhomes.com" + l.listing_url

            # pid from URL
            m = re.search(r"pid_(\d+)", l.listing_url)
            l.source_id = m.group(1) if m else ""

            details = card.get_text(" ", strip=True)
            beds, baths = self.parse_beds_baths(details)
            l.beds = beds or 0
            l.baths = baths or 0

            sqft_m = re.search(r"([\d,]+)\s*sq\s*ft", details, re.I)
            l.sqft = int(sqft_m.group(1).replace(",", "")) if sqft_m else None

            l.has_garage, l.garage_spaces = self.detect_garage(details)
            l.property_type = "sfr"
            l.fingerprint = self.fingerprint_listing(l.address, l.price)

            return l if l.address and l.price > 0 else None
        except Exception:
            return None

    def _from_dict(self, item: dict, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            l.zip_code = item.get("zip", zip_code)
            l.address = item.get("address", item.get("streetAddress", ""))
            l.city = item.get("city", "Irvine")
            l.price = int(item.get("listingPrice", item.get("price", 0)))
            l.beds = float(item.get("bedrooms", 0))
            l.baths = float(item.get("bathrooms", 0))
            l.sqft = item.get("squareFeet") or item.get("sqft")
            l.listing_url = item.get("url", item.get("listingUrl", ""))
            l.source_id = str(item.get("listingId", item.get("mlsNumber", "")))
            l.property_type = "sfr"
            garage_text = str(item.get("garage", item.get("parkingSpaces", "")))
            l.has_garage, l.garage_spaces = self.detect_garage(garage_text)
            l.agent_name = item.get("agentName")
            l.agent_phone = self.clean_phone(item.get("agentPhone"))
            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None
