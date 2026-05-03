"""Homesnap scraper — uses their public search JSON API."""
import json
from typing import List, Optional

from ..models import Listing
from .base import BaseScraper


class HomesnapScraper(BaseScraper):
    source_name = "homesnap"
    page_size = 20

    def search_url(self, zip_code: str, page: int) -> str:
        # Homesnap public search endpoint
        return (
            f"https://www.homesnap.com/api/portal/Listings/Search"
            f"?postalCode={zip_code}&propertyType=1&beds=3&baths=2&minSqft=1000"
            f"&page={page}&pageSize={self.page_size}"
        )

    async def fetch(self, url: str, headers=None):
        hdrs = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.homesnap.com/",
            "X-Requested-With": "XMLHttpRequest",
        }
        if headers:
            hdrs.update(headers)
        try:
            r = await self.client.get(url, headers=hdrs, follow_redirects=True)
            return r.status_code, r.text
        except Exception as exc:
            return 0, str(exc)

    def parse_search_page(self, body: str, zip_code: str) -> List[Listing]:
        try:
            data = json.loads(body)
        except Exception:
            return []

        items = data.get("listings", data.get("results", data.get("data", [])))
        if not isinstance(items, list):
            return []

        listings = []
        for item in items:
            l = self._from_item(item, zip_code)
            if l:
                listings.append(l)
        return listings

    def _from_item(self, item: dict, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            l.zip_code = str(item.get("zipCode", item.get("zip", zip_code)))
            l.address = item.get("streetAddress", item.get("address", ""))
            l.city = item.get("city", "Irvine")
            l.state = item.get("state", "CA")
            l.price = int(item.get("listPrice", item.get("price", 0)) or 0)
            l.beds = float(item.get("bedrooms", 0) or 0)
            l.baths = float(item.get("bathrooms", 0) or 0)
            l.sqft = item.get("squareFeet", item.get("squareFootage"))
            l.property_type = "sfr"
            l.listing_url = item.get("url", item.get("detailUrl", ""))
            if l.listing_url and not l.listing_url.startswith("http"):
                l.listing_url = f"https://www.homesnap.com{l.listing_url}"
            l.source_id = str(item.get("listingKey", item.get("id", "")))
            garage = str(item.get("garageSpaces", item.get("parkingSpaces", "")))
            l.has_garage, l.garage_spaces = self.detect_garage(garage)
            agent = item.get("listingAgent", {}) or {}
            l.agent_name = agent.get("agentName", agent.get("name"))
            l.agent_phone = self.clean_phone(agent.get("agentPhone", agent.get("phone")))
            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None
