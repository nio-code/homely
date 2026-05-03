from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from ..db import get_session
from ..models import Listing

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.get("")
def list_listings(
    pinned: Optional[bool] = None,
    status: Optional[str] = Query("approved", description="approved | pending | all"),
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    beds: Optional[float] = None,
    zip: Optional[str] = Query(None),
    session: Session = Depends(get_session),
) -> list[Listing]:
    stmt = select(Listing)
    if status and status != "all":
        stmt = stmt.where(Listing.status == status)
    if pinned is True:
        stmt = stmt.where(Listing.pinned_at.is_not(None))
    elif pinned is False:
        stmt = stmt.where(Listing.pinned_at.is_(None))
    if min_price is not None:
        stmt = stmt.where(Listing.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Listing.price <= max_price)
    if beds is not None:
        stmt = stmt.where(Listing.beds >= beds)
    if zip:
        stmt = stmt.where(Listing.zip == zip)
    stmt = stmt.order_by(Listing.pinned_at.desc().nulls_last(), Listing.price.desc())
    return session.exec(stmt).all()


@router.get("/{listing_id}")
def get_listing(listing_id: int, session: Session = Depends(get_session)) -> Listing:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    return listing
