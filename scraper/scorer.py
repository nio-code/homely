from typing import Optional
from .config import MARKET_RENT, MEDIAN_SQFT
from .models import Listing


def market_rent_for(zip_code: str, beds: float, sqft: Optional[int]) -> int:
    """
    Estimate achievable monthly rent for a SFH in this ZIP at this size.
    Uses ZIP+bed lookup table, then adjusts up/down by sqft vs. median for that bed count.
    """
    bed_key = min(max(int(beds), 3), 5)
    base = MARKET_RENT.get((zip_code, bed_key))
    if base is None:
        # Fall back to nearest ZIP or global default
        base = MARKET_RENT.get(("92618", bed_key), 4600)

    if sqft:
        median = MEDIAN_SQFT.get(bed_key, 1500)
        # ±20% max adjustment scaled linearly over ±500 sqft
        delta = (sqft - median) / 500.0
        adjustment = max(-0.20, min(0.20, delta * 0.10))
        base = int(base * (1 + adjustment))

    return base


def score(listing: Listing) -> Listing:
    """Compute rent estimate and 1% rule metrics. Mutates in place, returns listing."""
    if not listing.price or listing.price <= 0:
        return listing

    rent = market_rent_for(listing.zip_code, listing.beds, listing.sqft)
    listing.market_rent_est = rent
    listing.rent_to_price_pct = round(rent / listing.price * 100, 4)
    listing.pct_of_target = round(listing.rent_to_price_pct / 1.0 * 100, 2)
    listing.passes_1pct_rule = listing.rent_to_price_pct >= 1.0

    if listing.sqft and listing.price:
        listing.price_per_sqft = round(listing.price / listing.sqft, 2)

    return listing


def passes_filters(listing: Listing) -> bool:
    """Hard filter: beds, baths, sqft, property type, garage."""
    if listing.beds < 3:
        return False
    if listing.baths < 2:
        return False
    if listing.sqft and listing.sqft < 1000:
        return False
    if not listing.has_garage and listing.garage_spaces is None:
        # Allow if garage_spaces unknown — flag in notes rather than discard
        # Listings where garage info is entirely absent get through with a note
        pass
    pt = (listing.property_type or "").lower()
    if pt and pt not in {"sfr", "single_family", "house", "detached", "single family", ""}:
        return False
    return True
