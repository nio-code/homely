from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Listing(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_source_listing"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_id: str = Field(index=True)
    address: str
    city: str
    state: str
    zip: str = Field(index=True)
    price: int = Field(index=True)
    beds: float
    baths: float
    sqft: Optional[int] = None
    lot_sqft: Optional[int] = None
    property_type: Optional[str] = None
    listing_url: str
    agent_name: Optional[str] = None
    agent_phone: Optional[str] = None
    agent_email: Optional[str] = None
    notes: Optional[str] = None
    pinned_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)
