"""Trulia scraper — parses __NEXT_DATA__ JSON from Next.js pages."""
import json
import re
from typing import List, Optional

from ..models import Listing
from .base import BaseScraper


class TruliaScraper(BaseScraper):
    source_name = "trulia"
    page_size = 25

    def search_url(self, zip_code: str, page: int) -> str:
        return (
            f"https://www.trulia.com/for_sale/{zip_code}_zip/3+_beds/2+_ba/1000+_sqft/SINGLE-FAMILY_HOME_type/"
            f"p_{page}/"
        )

    def parse_search_page(self, html: str, zip_code: str) -> List[Listing]:
        soup = self.soup(html)
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag:
            return []
        try:
            data = json.loads(tag.string or "")
        except Exception:
            return []

        # Trulia buries listings under props.pageProps.searchResults.homes
        def dig(obj, *keys):
            for k in keys:
                if not isinstance(obj, dict):
                    return None
                obj = obj.get(k)
            return obj

        homes = (
            dig(data, "props", "pageProps", "searchResults", "homes")
            or dig(data, "props", "pageProps", "homes")
            or []
        )
        listings = []
        for h in homes:
            l = self._from_trulia_home(h, zip_code)
            if l:
                listings.append(l)
        return listings

    def _from_trulia_home(self, h: dict, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            loc = h.get("location", {})
            addr = loc.get("address", {})
            l.zip_code = addr.get("zip", zip_code)
            l.address = addr.get("streetAddress", h.get("streetAddress", ""))
            l.city = addr.get("city", "Irvine")
            l.state = addr.get("state", "CA")

            price_info = h.get("price", {})
            l.price = int(price_info.get("formattedPrice", "0").replace("$", "").replace(",", "") or 0)
            if l.price == 0:
                l.price = int(price_info.get("price", 0) or 0)

            l.beds = float(h.get("bedrooms", 0) or 0)
            l.baths = float(h.get("bathrooms", h.get("fullBathrooms", 0)) or 0)
            l.sqft = h.get("floorSpace", {}).get("formattedDimension", None)
            if isinstance(l.sqft, str):
                m = re.search(r"([\d,]+)", l.sqft)
                l.sqft = int(m.group(1).replace(",", "")) if m else None

            l.property_type = "sfr"
            l.listing_url = h.get("url", "")
            if l.listing_url and not l.listing_url.startswith("http"):
                l.listing_url = f"https://www.trulia.com{l.listing_url}"
            l.source_id = str(h.get("listingId", h.get("id", "")))

            # Garage — check tags/features
            tags = " ".join(str(t) for t in h.get("tags", []) + h.get("features", []))
            l.has_garage, l.garage_spaces = self.detect_garage(tags)

            # Agent
            agent = h.get("listingAgent", {}) or {}
            l.agent_name = agent.get("name")
            l.agent_phone = self.clean_phone(agent.get("phone"))

            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None
