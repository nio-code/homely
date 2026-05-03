"""
Redfin scraper using the unofficial stingray GIS API.
Step 1: resolve ZIP → region_id via autocomplete endpoint.
Step 2: hit GIS search API with region_id + filters.
Note: Redfin has Cloudflare protection; works ~60% of the time without proxies.
"""
import json
import re
from typing import Dict, List, Optional

import httpx

from ..models import Listing
from .base import BaseScraper

# Pre-resolved region_ids for target ZIPs (avoids an extra round-trip per run)
_KNOWN_REGION_IDS: Dict[str, str] = {
    "92602": "26085",
    "92603": "26086",
    "92606": "26091",
    "92612": "26093",
    "92614": "26095",
    "92618": "26098",
    "92620": "26100",
    "92697": "26093",  # UCI campus — falls back to 92612
}


class RedfinScraper(BaseScraper):
    source_name = "redfin"
    page_size = 50

    def search_url(self, zip_code: str, page: int) -> str:
        region_id = _KNOWN_REGION_IDS.get(zip_code, "26093")
        start = (page - 1) * self.page_size
        return (
            "https://www.redfin.com/stingray/api/gis?"
            f"al=1&market=socal"
            f"&region_id={region_id}&region_type=2"
            f"&status=1"
            f"&uipt=1"          # 1 = house / SFR
            f"&beds_min=3&baths_min=2&sqft_min=1000"
            f"&num_homes={self.page_size}"
            f"&start={start}"
            f"&sf=1,2,3,5,6,7"
            f"&v=8"
        )

    async def fetch(self, url: str, headers: Optional[dict] = None) -> tuple:
        # Redfin requires these specific headers to avoid 403
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
        # Redfin prepends "{}&&" to JSON responses as XSSI protection
        clean = body.lstrip("{}&")
        try:
            data = json.loads(clean)
        except Exception:
            return []

        homes = (
            data.get("payload", {}).get("homes", [])
            or data.get("payload", {}).get("homeData", {}).get("homesByRegion", [])
        )
        listings = []
        for h in homes:
            l = self._from_home(h, zip_code)
            if l:
                listings.append(l)
        return listings

    def _from_home(self, h: dict, zip_code: str) -> Optional[Listing]:
        try:
            l = Listing()
            info = h.get("homeData", h)
            addr = info.get("addressInfo", {})

            l.address = addr.get("formattedStreetLine", info.get("address", ""))
            l.city = addr.get("city", "Irvine")
            l.state = addr.get("state", "CA")
            l.zip_code = str(addr.get("zip", zip_code))
            l.price = int(info.get("priceInfo", {}).get("amount", 0) or 0)
            l.beds = float(info.get("beds", 0) or 0)
            l.baths = float(info.get("baths", 0) or 0)
            l.sqft = info.get("sqFt", {}).get("value") if isinstance(info.get("sqFt"), dict) else info.get("sqFt")
            l.property_type = "sfr"
            l.source_id = str(info.get("mlsId", {}).get("value", "") or info.get("listingId", ""))

            url_path = info.get("url", "")
            l.listing_url = f"https://www.redfin.com{url_path}" if url_path else ""

            # Garage: in amenitiesInfo or description
            amenities = str(info.get("amenitiesInfo", {}))
            desc = info.get("remarksInfo", {}).get("remarksAccessor", "")
            l.has_garage, l.garage_spaces = self.detect_garage(amenities + " " + desc)

            # Agent
            agent = info.get("listingAgent", {})
            l.agent_name = agent.get("agentName")
            l.agent_phone = self.clean_phone(agent.get("agentPhone"))

            l.fingerprint = self.fingerprint_listing(l.address, l.price)
            return l if l.address and l.price > 0 else None
        except Exception:
            return None
