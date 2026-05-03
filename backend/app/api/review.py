from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from ..db import get_session
from ..models import Listing

router = APIRouter(prefix="/api/listings", tags=["review"])


@router.post("/{listing_id}/approve")
def approve(listing_id: int, session: Session = Depends(get_session)) -> Listing:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    listing.status = "approved"
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing


@router.delete("/{listing_id}")
def reject(listing_id: int, session: Session = Depends(get_session)) -> dict:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    session.delete(listing)
    session.commit()
    return {"deleted": listing_id}
