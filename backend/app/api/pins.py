from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from ..db import get_session
from ..models import Listing, utcnow
from ..telegram.notifier import send_pin

router = APIRouter(prefix="/api/listings", tags=["pins"])


@router.post("/{listing_id}/pin")
async def pin_listing(listing_id: int, session: Session = Depends(get_session)) -> dict:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    listing.pinned_at = utcnow()
    session.add(listing)
    session.commit()
    session.refresh(listing)
    telegram_ok = await send_pin(listing)
    return {"listing": listing, "telegram_sent": telegram_ok}


@router.delete("/{listing_id}/pin")
def unpin_listing(listing_id: int, session: Session = Depends(get_session)) -> Listing:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    listing.pinned_at = None
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing
