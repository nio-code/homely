"""
HTTP sink — POSTs qualified listings to POST /api/listings/ingest in batches.
Falls back gracefully if the backend is not running.
"""
import dataclasses
import logging
from typing import List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError
import json

from .models import Listing

log = logging.getLogger("homely.sink")

DEFAULT_API_URL = "http://localhost:8000/api/listings/ingest"
BATCH_SIZE = 50


def _listing_to_dict(l: Listing) -> dict:
    d = dataclasses.asdict(l)
    # scraper uses zip_code; backend IngestItem expects zip_code
    # (already aligned — IngestItem.zip_code maps to DB Listing.zip)
    return d


def post_to_api(
    listings: List[Listing],
    api_url: str = DEFAULT_API_URL,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """
    POST listings to the backend in batches of `batch_size`.
    Returns aggregated {inserted, updated, skipped, total}.
    Returns empty dict and logs a warning if backend is unreachable.
    """
    totals = {"inserted": 0, "updated": 0, "skipped": 0, "total": 0}

    if not listings:
        return totals

    for i in range(0, len(listings), batch_size):
        batch = listings[i : i + batch_size]
        payload = json.dumps([_listing_to_dict(l) for l in batch]).encode()

        req = Request(
            api_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
                totals["inserted"] += body.get("inserted", 0)
                totals["updated"] += body.get("updated", 0)
                totals["skipped"] += body.get("skipped", 0)
                totals["total"] += body.get("total", 0)
                log.info(
                    "Ingest batch %d-%d → inserted=%d updated=%d skipped=%d",
                    i + 1, i + len(batch),
                    body.get("inserted", 0),
                    body.get("updated", 0),
                    body.get("skipped", 0),
                )
        except URLError as exc:
            log.warning(
                "Backend unreachable (%s) — batch %d-%d skipped. "
                "Start the backend with: cd backend && uvicorn app.main:app --reload",
                exc.reason if hasattr(exc, "reason") else exc,
                i + 1, i + len(batch),
            )
            totals["skipped"] += len(batch)
        except Exception as exc:
            log.warning("Ingest error on batch %d-%d: %s", i + 1, i + len(batch), exc)
            totals["skipped"] += len(batch)

    return totals
