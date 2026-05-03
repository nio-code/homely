"""
SQLite raw event store + JSONL qualified listings writer.
Thread/async-safe via a dedicated writer coroutine pattern (single writer).
"""
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import List

from .models import Listing, RawEvent


class RawStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS raw_events (
                event_id        TEXT PRIMARY KEY,
                scraped_at      TEXT NOT NULL,
                source          TEXT NOT NULL,
                source_url      TEXT,
                source_listing_id TEXT,
                raw_json        TEXT NOT NULL,
                fingerprint     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_fingerprint ON raw_events(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_source ON raw_events(source);
        """)
        self._conn.commit()

    def seen(self, fingerprint: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM raw_events WHERE fingerprint = ? LIMIT 1", (fingerprint,)
        ).fetchone()
        return row is not None

    def insert(self, event: RawEvent) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO raw_events
               (event_id, scraped_at, source, source_url, source_listing_id, raw_json, fingerprint)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.scraped_at,
                event.source,
                event.source_url,
                event.source_listing_id,
                json.dumps(event.raw),
                event.fingerprint,
            ),
        )
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]

    def close(self) -> None:
        self._conn.close()


class QualifiedWriter:
    """Appends scored listings to a JSONL file and a summary JSON."""

    def __init__(self, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = out_dir / "qualified_listings.jsonl"
        self.summary_path = out_dir / "run_summary.json"
        self._listings: List[Listing] = []

    def write(self, listing: Listing) -> None:
        self._listings.append(listing)
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(asdict(listing)) + "\n")

    def flush_summary(self, total_scraped: int, total_raw: int) -> None:
        summary = {
            "total_scraped_pages": total_scraped,
            "total_raw_events": total_raw,
            "total_qualified": len(self._listings),
            "passes_1pct_rule": sum(1 for l in self._listings if l.passes_1pct_rule),
            "top_by_yield": [
                {
                    "address": l.address,
                    "zip": l.zip_code,
                    "price": l.price,
                    "beds": l.beds,
                    "baths": l.baths,
                    "sqft": l.sqft,
                    "market_rent_est": l.market_rent_est,
                    "rent_to_price_pct": l.rent_to_price_pct,
                    "pct_of_target": l.pct_of_target,
                    "agent_name": l.agent_name,
                    "agent_phone": l.agent_phone,
                    "listing_url": l.listing_url,
                }
                for l in sorted(
                    self._listings,
                    key=lambda x: x.rent_to_price_pct or 0,
                    reverse=True,
                )[:50]
            ],
        }
        with open(self.summary_path, "w") as f:
            json.dump(summary, f, indent=2)
