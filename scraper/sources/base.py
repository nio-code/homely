"""Base scraper — all source scrapers inherit from this."""
import hashlib
import json
import random
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from ..config import USER_AGENTS
from ..models import Listing, RawEvent


class BaseScraper(ABC):
    source_name: str = ""
    page_size: int = 40

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    # ------------------------------------------------------------------
    # Subclasses implement these two
    # ------------------------------------------------------------------

    @abstractmethod
    def search_url(self, zip_code: str, page: int) -> str:
        """Build the paginated search URL for this source."""

    @abstractmethod
    def parse_search_page(self, html: str, zip_code: str) -> List[Listing]:
        """Extract listings from a search-results HTML page."""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def fetch(self, url: str, headers: Optional[dict] = None) -> Tuple[int, str]:
        hdrs = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }
        if headers:
            hdrs.update(headers)
        try:
            r = await self.client.get(url, headers=hdrs, follow_redirects=True)
            return r.status_code, r.text
        except Exception as exc:
            return 0, str(exc)

    async def scrape(self, zip_code: str, page: int) -> Tuple[List[Listing], List[RawEvent]]:
        """Fetch one search page and return (listings, raw_events)."""
        url = self.search_url(zip_code, page)
        status, body = await self.fetch(url)
        if status != 200:
            return [], []

        raw = RawEvent(
            source=self.source_name,
            source_url=url,
            raw={"status": status, "body_len": len(body)},
            fingerprint=self._fingerprint(url),
        )
        listings = self.parse_search_page(body, zip_code)
        for l in listings:
            l.source = self.source_name
        return listings, [raw]

    # ------------------------------------------------------------------
    # Parsing utilities
    # ------------------------------------------------------------------

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def extract_json_ld(self, html: str) -> List[dict]:
        """Extract all JSON-LD blocks from a page."""
        soup = self.soup(html)
        results = []
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)
            except Exception:
                pass
        return results

    def extract_embedded_json(self, html: str, var_name: str) -> Optional[dict]:
        """Extract a window.VAR_NAME = {...} JavaScript object."""
        pattern = rf'(?:window\.)?{re.escape(var_name)}\s*=\s*(\{{.*?\}});'
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        return None

    def clean_phone(self, raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        if len(digits) == 11 and digits[0] == "1":
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return raw.strip() or None

    def detect_garage(self, text: str) -> Tuple[bool, Optional[int]]:
        """Return (has_garage, spaces_count) from any text blob."""
        low = text.lower()
        if "garage" not in low and "parking" not in low:
            return False, None
        m = re.search(r"(\d)\s*(?:car\s+)?garage", low)
        spaces = int(m.group(1)) if m else None
        return True, spaces

    def parse_beds_baths(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        beds = baths = None
        m = re.search(r"(\d+\.?\d*)\s*(?:bed|br|bd)", text.lower())
        if m:
            beds = float(m.group(1))
        m = re.search(r"(\d+\.?\d*)\s*(?:bath|ba)", text.lower())
        if m:
            baths = float(m.group(1))
        return beds, baths

    def parse_price(self, text: str) -> Optional[int]:
        clean = re.sub(r"[^\d]", "", text.replace(",", ""))
        return int(clean) if clean.isdigit() and int(clean) > 0 else None

    def _fingerprint(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:16]

    def fingerprint_listing(self, address: str, price: int) -> str:
        return self._fingerprint(f"{address.lower().strip()}|{price}")
