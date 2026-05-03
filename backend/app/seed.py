"""Idempotent seed loader.

Reads backend/data/listings.json and upserts each row by (source, source_id).
Run with: `python -m app.seed` from the backend/ directory.

Schema: see backend/app/models.py:Listing. Required fields per row:
  source, source_id, address, city, state, zip, price, beds, baths, listing_url
Nullable: sqft, lot_sqft, property_type, agent_name, agent_phone, agent_email, notes.
"""
import json
from sqlmodel import Session, select
from .config import DATA_DIR
from .db import engine, init_db
from .models import Listing


def load_seed() -> int:
    init_db()
    path = DATA_DIR / "listings.json"
    rows = json.loads(path.read_text())
    n = 0
    with Session(engine) as session:
        for row in rows:
            existing = session.exec(
                select(Listing).where(
                    Listing.source == row["source"],
                    Listing.source_id == row["source_id"],
                )
            ).first()
            if existing:
                for k, v in row.items():
                    setattr(existing, k, v)
                session.add(existing)
            else:
                session.add(Listing(**row))
            n += 1
        session.commit()
    return n


if __name__ == "__main__":
    count = load_seed()
    print(f"Inserted/updated {count} listings.")
