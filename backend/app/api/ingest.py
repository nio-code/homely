"""
POST /api/listings/ingest
Accepts a batch of listings from the scraper, upserts on (source, source_id).
Extra scraper-only fields (scoring, garage, etc.) are serialised into notes.
"""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Listing

router = APIRouter(prefix="/api/listings", tags=["ingest"])


class IngestItem(BaseModel):
    source: str
    source_id: str
    address: str
    city: str = "Irvine"
    state: str = "CA"
    zip_code: str          # scraper uses zip_code; we map to model's zip
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

    # Scoring fields — packed into notes so they survive without a schema change
    market_rent_est: Optional[int] = None
    rent_to_price_pct: Optional[float] = None
    pct_of_target: Optional[float] = None
    price_per_sqft: Optional[float] = None
    passes_1pct_rule: bool = False
    has_garage: bool = False
    garage_spaces: Optional[int] = None

    notes: Optional[str] = None


class IngestResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    total: int


@router.post("/ingest", response_model=IngestResponse)
def ingest_listings(
    items: List[IngestItem],
    session: Session = Depends(get_session),
) -> IngestResponse:
    inserted = updated = skipped = 0

    for item in items:
        # Pack scoring + garage fields into notes JSON
        meta = {
            "market_rent_est": item.market_rent_est,
            "rent_to_price_pct": item.rent_to_price_pct,
            "pct_of_target": item.pct_of_target,
            "price_per_sqft": item.price_per_sqft,
            "passes_1pct_rule": item.passes_1pct_rule,
            "has_garage": item.has_garage,
            "garage_spaces": item.garage_spaces,
        }
        notes_parts = []
        if item.notes:
            notes_parts.append(item.notes)
        notes_parts.append(json.dumps(meta))
        notes = " | ".join(notes_parts)

        # Upsert on (source, source_id)
        stmt = select(Listing).where(
            Listing.source == item.source,
            Listing.source_id == item.source_id,
        )
        existing = session.exec(stmt).first()

        if existing:
            # Update price and agent info; preserve pinned_at
            existing.price = item.price
            existing.beds = item.beds
            existing.baths = item.baths
            existing.sqft = item.sqft
            existing.agent_name = item.agent_name
            existing.agent_phone = item.agent_phone
            existing.agent_email = item.agent_email
            existing.notes = notes
            existing.listing_url = item.listing_url or existing.listing_url
            session.add(existing)
            updated += 1
        else:
            listing = Listing(
                source=item.source,
                source_id=item.source_id,
                address=item.address,
                city=item.city,
                state=item.state,
                zip=item.zip_code,
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
            )
            session.add(listing)
            inserted += 1

    try:
        session.commit()
    except Exception:
        session.rollback()
        skipped = len(items)
        inserted = updated = 0

    return IngestResponse(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        total=len(items),
    )
