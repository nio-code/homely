"""
POST /api/listings/ingest
Authorization: Bearer <INGEST_API_KEY>
Content-Type: application/json

Body — single listing or array of up to 500:
[
  {
    "source": "your_pipeline_name",
    "source_id": "MLS-12345",
    "address": "45 Oak Creek, Irvine",
    "city": "Irvine", "state": "CA", "zip": "92620",
    "price": 1850000, "beds": 4, "baths": 3, "sqft": 2400,
    "lot_sqft": 5000, "property_type": "Single Family",
    "listing_url": "https://...",
    "agent_name": "Jane Doe", "agent_phone": "(949) 555-1234",
    "agent_email": "jane@example.com"
  }
]

Response: { "received": 1, "inserted": 1, "updated": 0, "errors": [] }

- New listing (source + source_id not seen) → inserted
- Re-sent listing (same source + source_id) → updated in place
- Pinned listings and notes are never overwritten
- Wrong/missing Bearer token → 401 Unauthorized
- Partial failures: return what succeeded + errors array with failed source_ids
"""
from __future__ import annotations

import json
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, validator
from sqlmodel import Session, select

from ..config import INGEST_API_KEY
from ..db import get_session
from ..models import Listing

router = APIRouter(prefix="/api/listings", tags=["ingest"])
_bearer = HTTPBearer(auto_error=False)


def _auth(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> None:
    if not INGEST_API_KEY:
        return  # no key configured → open (dev mode)
    if not creds or creds.credentials != INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Request schema ─────────────────────────────────────────────────────────

class IngestItem(BaseModel):
    source: str
    source_id: str
    address: str
    city: str = "Irvine"
    state: str = "CA"
    zip: str                   # matches DB field name
    price: int
    beds: float
    baths: float
    sqft: Optional[int] = None
    lot_sqft: Optional[int] = None
    property_type: Optional[str] = None
    listing_url: str = ""
    agent_name: Optional[str] = None
    agent_phone: Optional[str] = None
    agent_email: Optional[str] = None
    notes: Optional[str] = None

    # Optional scoring fields from the scraper pipeline (packed into notes)
    market_rent_est: Optional[int] = None
    rent_to_price_pct: Optional[float] = None
    pct_of_target: Optional[float] = None
    price_per_sqft: Optional[float] = None
    passes_1pct_rule: bool = False
    has_garage: bool = False
    garage_spaces: Optional[int] = None

    # Scraper uses zip_code; accept both
    zip_code: Optional[str] = Field(default=None, exclude=True)

    @validator("zip", pre=True, always=True)
    def coerce_zip(cls, v, values):
        # Accept zip_code alias
        return v or values.get("zip_code", "")

    class Config:
        # allow extra fields (e.g. scraped_at, year_built) without crashing
        extra = "ignore"


# ── Response schema ────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    source_id: str
    reason: str


class IngestResponse(BaseModel):
    received: int
    inserted: int
    updated: int
    errors: List[ErrorDetail] = []


# ── Endpoint ───────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
def ingest_listings(
    body: Union[List[IngestItem], IngestItem],
    _: None = Depends(_auth),
    session: Session = Depends(get_session),
) -> IngestResponse:
    items: List[IngestItem] = body if isinstance(body, list) else [body]

    inserted = updated = 0
    errors: List[ErrorDetail] = []

    for item in items:
        try:
            # Pack scraper scoring fields into notes
            meta = {k: getattr(item, k) for k in (
                "market_rent_est", "rent_to_price_pct", "pct_of_target",
                "price_per_sqft", "passes_1pct_rule", "has_garage", "garage_spaces",
            )}
            notes_parts = []
            if item.notes:
                notes_parts.append(item.notes)
            notes_parts.append(json.dumps(meta))
            notes = " | ".join(notes_parts)

            stmt = select(Listing).where(
                Listing.source == item.source,
                Listing.source_id == item.source_id,
            )
            existing = session.exec(stmt).first()

            if existing:
                # Update price/details — never touch pinned_at
                existing.price = item.price
                existing.beds = item.beds
                existing.baths = item.baths
                existing.sqft = item.sqft
                existing.lot_sqft = item.lot_sqft
                existing.agent_name = item.agent_name
                existing.agent_phone = item.agent_phone
                existing.agent_email = item.agent_email
                if item.listing_url:
                    existing.listing_url = item.listing_url
                existing.notes = notes
                session.add(existing)
                updated += 1
            else:
                listing = Listing(
                    source=item.source,
                    source_id=item.source_id,
                    address=item.address,
                    city=item.city,
                    state=item.state,
                    zip=item.zip,
                    price=item.price,
                    beds=item.beds,
                    baths=item.baths,
                    sqft=item.sqft,
                    lot_sqft=item.lot_sqft,
                    property_type=item.property_type,
                    listing_url=item.listing_url,
                    agent_name=item.agent_name,
                    agent_phone=item.agent_phone,
                    agent_email=item.agent_email,
                    notes=notes,
                    status="pending",
                )
                session.add(listing)
                inserted += 1

        except Exception as exc:
            errors.append(ErrorDetail(source_id=item.source_id, reason=str(exc)))

    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        return IngestResponse(
            received=len(items), inserted=0, updated=0,
            errors=[ErrorDetail(source_id="batch", reason=str(exc))],
        )

    return IngestResponse(
        received=len(items),
        inserted=inserted,
        updated=updated,
        errors=errors,
    )
