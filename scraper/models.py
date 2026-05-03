from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RawEvent:
    """One scraped page/listing as-is, before normalization."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scraped_at: str = field(default_factory=_now)
    source: str = ""
    source_url: str = ""
    source_listing_id: str = ""
    raw: dict = field(default_factory=dict)
    fingerprint: str = ""  # sha256 of address+price — dedup key


@dataclass
class Listing:
    """Normalized, filtered, and scored listing."""
    # Identity
    source: str = ""
    source_id: str = ""
    address: str = ""
    city: str = "Irvine"
    state: str = "CA"
    zip_code: str = ""
    listing_url: str = ""

    # Property
    price: int = 0
    beds: float = 0.0
    baths: float = 0.0
    sqft: Optional[int] = None
    lot_sqft: Optional[int] = None
    property_type: Optional[str] = None
    year_built: Optional[int] = None
    garage_spaces: Optional[int] = None
    has_garage: bool = False
    days_on_market: Optional[int] = None

    # Agent
    agent_name: Optional[str] = None
    agent_phone: Optional[str] = None
    agent_email: Optional[str] = None
    brokerage: Optional[str] = None

    # Scoring (set by scorer.py)
    market_rent_est: Optional[int] = None       # $/month
    rent_to_price_pct: Optional[float] = None   # (rent/price)*100; 1% rule needs >= 1.0
    pct_of_target: Optional[float] = None       # how close to 1% target (100 = exactly 1%)
    price_per_sqft: Optional[float] = None
    passes_1pct_rule: bool = False

    notes: Optional[str] = None
    scraped_at: str = field(default_factory=_now)
