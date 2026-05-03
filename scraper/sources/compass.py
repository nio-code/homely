"""
Compass scraper.
Search URL: https://www.compass.com/homes-for-sale/irvine-ca/beds/3/baths/2/sqft/1000/type/house/
Also tries their internal search API endpoint.
"""
import re
from typing import List, Optional

from ..models import Listing
from .base import BaseScraper


class CompassScraper(BaseScraper):
    source_name = "compass"
    page_size = 20

    def search_url(self, zip_code: str, page: int) -> str:
        # Compass URL-based filters; pagination via ?page=N
        return (
            f"https://www.compass.com/homes-for-sale/irvine-ca/"
            f"beds/3/baths/2/sqft/1000/type/house/"
            f"?zipCode={zip_code}&page={page}"
        )

    def parse_search_page(self, html: str, zip_code: str) -> List[Listing]:
        listings = []

        # Strategy 1: JSON-LD
        for ld in self.extract_json_ld(html):
            type_ = ld.get("@type", "")
            if "RealEstate" in type_ or "House" in type_ or "Residence" in type_:
                l = self._from_json_ld(ld, zip_code)
                if l:
                    listings.append(l)

        # Strategy 2: __NEXT_DATA__ (Next.js apps embed page props here)
        if not listings:
            soup = self.soup(html)
            tag = soup.find("script", id="__NEXT_DATA__")
            if tag:
                import json
                try:
                    data = json.loads(tag.string or "")
                    props = data.get("props", {}).get("pageProps", {})
                    for key in ("listings", "searchResults", "homes"):
                        items = props.get(key, [])
                        if isinstance(items, list):
                            for item in items:
                                l = self._from_next_item(item, zip_code)
                                if l:
                                    listings.append(l)
                except Exception:
                    pass

        # Strategy 3: listing cards
        if not listings:
            soup = self.soup(html)
            cards = soup.select("[data-tn='listing-card'], .uc-listingCard, .listingCard-container")
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
            l.state = addr.get("addressRegion", "CA")
            l.listing_url = ld.get("url", "")
            l.property_type = "sfr"
            l.source_id = ld.get("identifier", {}).get("value", "")

            price_info = ld.get("offers", ld.get("price", {}))
            if isinstance(price_info, dict):
                l.price = self.parse_price(str(price_info.get("price", 0))) or 0
            elif isinstance(price_info, (int, float)):
                l.price = int(price_info)

            desc = ld.get("description", "")
            beds, baths = self.parse_beds_baths(desc)
            l.beds = beds or 0
            l.baths = baths or 0
            l.has_garage, l.garage_spaces = self.detect_garage(desc)

            # Agent
            agent = ld.get("agent", {})
            if isinstance(agent, list):
                agent = agent[0] if agent else {}
            l.agent_name = agent.get("name")
            l.agent_phone = self.clean_phone(agent.get("telephone"))
            l.agent_email = agent.get("email")

            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None

    def _from_next_item(self, item: dict, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            loc = item.get("location", {})
            l.zip_code = loc.get("zip", item.get("zip", zip_code))
            l.address = loc.get("streetAddress", item.get("streetAddress", item.get("address", "")))
            l.city = loc.get("city", "Irvine")
            l.price = int(item.get("listingPrice", item.get("price", 0)))
            l.beds = float(item.get("bedrooms", item.get("beds", 0)))
            l.baths = float(item.get("bathrooms", item.get("baths", 0)))
            l.sqft = item.get("squareFootage", item.get("sqft"))
            l.listing_url = item.get("listingUrl", item.get("url", ""))
            l.source_id = str(item.get("listingId", item.get("id", "")))
            l.property_type = "sfr"
            garage = item.get("parkingSpaces", item.get("garageSpaces", ""))
            l.has_garage, l.garage_spaces = self.detect_garage(str(garage))
            agent = item.get("listingAgent", item.get("agent", {}))
            if isinstance(agent, dict):
                l.agent_name = agent.get("name")
                l.agent_phone = self.clean_phone(agent.get("phone", agent.get("telephone")))
                l.agent_email = agent.get("email")
            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None

    def _from_card(self, card, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            l.zip_code = zip_code
            l.property_type = "sfr"

            price_el = card.select_one("[data-tn='listing-card-price'], .listingCard-price")
            l.price = self.parse_price(price_el.get_text()) if price_el else 0

            addr_el = card.select_one("[data-tn='listing-card-address'], .listingCard-address")
            l.address = addr_el.get_text(strip=True) if addr_el else ""

            link = card.select_one("a[href]")
            href = link["href"] if link else ""
            l.listing_url = href if href.startswith("http") else f"https://www.compass.com{href}"

            m = re.search(r"/([A-Z0-9_]{6,})[/_]", l.listing_url)
            l.source_id = m.group(1) if m else ""

            details = card.get_text(" ", strip=True)
            beds, baths = self.parse_beds_baths(details)
            l.beds = beds or 0
            l.baths = baths or 0
            sqft_m = re.search(r"([\d,]+)\s*sq\s*ft", details, re.I)
            l.sqft = int(sqft_m.group(1).replace(",", "")) if sqft_m else None
            l.has_garage, l.garage_spaces = self.detect_garage(details)
            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None
