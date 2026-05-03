"""
Redfin scraper using the unofficial stingray GIS API.
Region IDs confirmed by probing the Redfin API for SoCal neighborhoods.
"""
import json
import re
from typing import Dict, List, Optional

from ..models import Listing
from .base import BaseScraper

# Confirmed region_id → ZIP mapping (region_type=2, market=socal)
REGION_IDS: Dict[str, int] = {
    "92602": 38398,
    "92603": 38399,
    "92606": 38402,
    "92612": 38406,
    "92614": 38407,
    "92618": 38411,
    "92620": 38413,
    "92697": 38406,  # UCI campus — use 92612 proxy
}


class RedfinScraper(BaseScraper):
    source_name = "redfin"
    page_size = 50

    def search_url(self, zip_code: str, page: int) -> str:
        region_id = REGION_IDS.get(zip_code, 38411)
        start = (page - 1) * self.page_size
        return (
            "https://www.redfin.com/stingray/api/gis?"
            f"al=1&market=socal"
            f"&region_id={region_id}&region_type=2"
            f"&status=1"
            f"&uipt=1"
            f"&beds_min=3&baths_min=2&sqft_min=1000"
            f"&num_homes={self.page_size}"
            f"&start={start}"
            f"&sf=1,2,3,5,6,7"
            f"&v=8"
        )

    async def fetch(self, url: str, headers: Optional[dict] = None) -> tuple:
        hdrs = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.redfin.com/",
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
        # Strip Redfin XSSI prefix — everything before first '{"version"'
        m = re.search(r'\{"version"', body)
        if not m:
            return []
        try:
            data = json.loads(body[m.start():])
        except Exception:
            return []

        homes = data.get("payload", {}).get("homes", [])
        listings = []
        for h in homes:
            l = self._from_home(h, zip_code)
            if l:
                listings.append(l)
        return listings

    def _from_home(self, h: dict, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()

            # Address fields — all nested under value/level dicts
            l.address = (h.get("streetLine") or {}).get("value", "")
            l.city = h.get("city", "Irvine")
            l.state = h.get("state", "CA")
            l.zip_code = str(h.get("zip") or zip_code)

            l.price = int((h.get("price") or {}).get("value", 0) or 0)
            l.beds = float(h.get("beds", 0) or 0)
            l.baths = float(h.get("baths", 0) or 0)

            sqft_block = h.get("sqFt") or {}
            l.sqft = sqft_block.get("value") if isinstance(sqft_block, dict) else None

            lot_block = h.get("lotSize") or {}
            l.lot_sqft = lot_block.get("value") if isinstance(lot_block, dict) else None

            year_block = h.get("yearBuilt") or {}
            l.year_built = year_block.get("value") if isinstance(year_block, dict) else None

            dom_block = h.get("dom") or {}
            l.days_on_market = dom_block.get("value") if isinstance(dom_block, dict) else None

            l.property_type = "sfr"

            url_path = h.get("url", "")
            l.listing_url = f"https://www.redfin.com{url_path}" if url_path else ""

            mls_block = h.get("mlsId") or {}
            l.source_id = str(mls_block.get("value", "") or h.get("listingId", ""))

            # Agent info
            agent = h.get("listingAgent") or {}
            l.agent_name = agent.get("name")
            l.agent_phone = self.clean_phone(agent.get("phone") or agent.get("agentPhone"))
            l.brokerage = agent.get("officeName")

            # Garage: Redfin doesn't expose in search results — mark unknown
            l.has_garage = False
            l.garage_spaces = None

            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None
