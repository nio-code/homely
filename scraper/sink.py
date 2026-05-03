"""
HTTP sink — POSTs qualified listings to POST /api/listings/ingest in batches.
Sends Authorization: Bearer <api_key>. Falls back gracefully if backend is down.
"""
import dataclasses
import json
import logging
import os
from typing import List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .models import Listing

log = logging.getLogger("homely.sink")

DEFAULT_API_URL = os.getenv("INGEST_URL", "http://localhost:8000/api/listings/ingest")
DEFAULT_API_KEY = os.getenv("INGEST_API_KEY", "key1")
BATCH_SIZE = 500  # spec allows up to 500 per call


def _listing_to_dict(l: Listing) -> dict:
    d = dataclasses.asdict(l)
    # Rename zip_code → zip to match the IngestItem schema
    if "zip_code" in d:
        d["zip"] = d.pop("zip_code")
    return d


def post_to_api(
    listings: List[Listing],
    api_url: str = DEFAULT_API_URL,
    api_key: str = DEFAULT_API_KEY,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """
    POST listings to the backend in batches (default 500 — spec max).
    Returns aggregated {received, inserted, updated, errors}.
    Logs a warning and returns counts if backend is unreachable.
    """
    totals: dict = {"received": 0, "inserted": 0, "updated": 0, "errors": []}

    if not listings:
        return totals

    for i in range(0, len(listings), batch_size):
        batch = listings[i : i + batch_size]
        payload = json.dumps([_listing_to_dict(l) for l in batch]).encode()

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = Request(api_url, data=payload, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
                totals["received"] += body.get("received", 0)
                totals["inserted"] += body.get("inserted", 0)
                totals["updated"] += body.get("updated", 0)
                totals["errors"].extend(body.get("errors", []))
                log.info(
                    "Ingest batch %d-%d → received=%d inserted=%d updated=%d errors=%d",
                    i + 1, i + len(batch),
                    body.get("received", 0),
                    body.get("inserted", 0),
                    body.get("updated", 0),
                    len(body.get("errors", [])),
                )
        except URLError as exc:
            reason = exc.reason if hasattr(exc, "reason") else str(exc)
            log.warning(
                "Backend unreachable (%s) — batch %d-%d skipped. "
                "Start backend: cd backend && uvicorn app.main:app --reload",
                reason, i + 1, i + len(batch),
            )
        except Exception as exc:
            log.warning("Ingest error on batch %d-%d: %s", i + 1, i + len(batch), exc)

    return totals
