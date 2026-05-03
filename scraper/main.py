"""
Homely scraper — 10 asyncio workers, 10 sources, target 500 qualified listings.

Usage:
    python -m scraper.main
    python -m scraper.main --target 500 --workers 10 --zips 92618,92612
    python -m scraper.main --api http://localhost:8000/api/listings/ingest
"""
import argparse
import asyncio
import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple, Type

import httpx

from .config import (
    CONCURRENCY,
    PAGES_PER_SOURCE_ZIP,
    REQUEST_TIMEOUT,
    SOURCE_CONCURRENCY,
    TARGET_QUALIFIED,
    TARGET_ZIPS,
)
from .models import Listing, RawEvent
from .scorer import passes_filters, score
from .sink import DEFAULT_API_URL, post_to_api
from .sources import ALL_SCRAPERS
from .sources.base import BaseScraper
from .storage import QualifiedWriter, RawStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("homely.scraper")

WORKSPACE = Path(__file__).parent.parent
DB_PATH = WORKSPACE / "datafeed" / "raw_events.db"
OUT_DIR = WORKSPACE / "datafeed"


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

async def worker(
    worker_id: int,
    job_queue: asyncio.Queue,
    result_queue: asyncio.Queue,
    source_semaphores: dict,
    stop_event: asyncio.Event,
) -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=False) as client:
        while not stop_event.is_set():
            try:
                scraper_cls, zip_code, page = job_queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.2)
                continue

            source = scraper_cls.source_name
            sem = source_semaphores.get(source, asyncio.Semaphore(2))
            scraper: BaseScraper = scraper_cls(client)

            async with sem:
                try:
                    listings, raw_events = await scraper.scrape(zip_code, page)
                    await result_queue.put((listings, raw_events, source, zip_code, page))
                    log.info(
                        "worker-%d  %-18s  zip=%-7s  page=%d  found=%d",
                        worker_id, source, zip_code, page, len(listings),
                    )
                except Exception as exc:
                    log.warning("worker-%d  %s  zip=%s  page=%d  ERROR: %s",
                                worker_id, source, zip_code, page, exc)

            job_queue.task_done()
            # Polite delay per source
            await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Result processor (single coroutine — serialises all DB writes)
# ---------------------------------------------------------------------------

async def result_processor(
    result_queue: asyncio.Queue,
    raw_store: RawStore,
    qualified_writer: QualifiedWriter,
    target: int,
    stop_event: asyncio.Event,
) -> int:
    qualified_count = 0
    seen_fingerprints = set()

    while not stop_event.is_set() or not result_queue.empty():
        try:
            listings, raw_events, source, zip_code, page = await asyncio.wait_for(
                result_queue.get(), timeout=1.0
            )
        except asyncio.TimeoutError:
            continue

        # Store raw events
        for ev in raw_events:
            raw_store.insert(ev)

        # Filter, deduplicate, score
        for listing in listings:
            fp = listing.fingerprint
            if fp in seen_fingerprints or raw_store.seen(fp + "_q"):
                continue
            seen_fingerprints.add(fp)

            if not passes_filters(listing):
                continue

            listing = score(listing)

            # Garage: skip if garage info explicitly absent and lot size suggests no garage
            # (we allow garage_unknown — marked in notes)
            if not listing.has_garage and listing.garage_spaces is None:
                listing.notes = (listing.notes or "") + " [garage:unknown]"

            qualified_writer.write(listing)
            qualified_count += 1

            log.info(
                "  QUALIFIED #%-4d  %-35s  $%-9s  rent=$%s/mo  yield=%.2f%%  phone=%s",
                qualified_count,
                listing.address[:35],
                f"{listing.price:,}",
                f"{listing.market_rent_est:,}" if listing.market_rent_est else "?",
                listing.rent_to_price_pct or 0,
                listing.agent_phone or "—",
            )

            if qualified_count >= target:
                log.info("Target of %d qualified listings reached — stopping.", target)
                stop_event.set()
                break

        result_queue.task_done()

    return qualified_count


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run(target: int, workers: int, zips: List[str], api_url: Optional[str] = None) -> None:
    raw_store = RawStore(DB_PATH)
    qualified_writer = QualifiedWriter(OUT_DIR)
    stop_event = asyncio.Event()

    # Build job queue: (scraper_cls, zip_code, page)
    job_queue: asyncio.Queue = asyncio.Queue()
    for page in range(1, PAGES_PER_SOURCE_ZIP + 1):
        for zip_code in zips:
            for scraper_cls in ALL_SCRAPERS:
                await job_queue.put((scraper_cls, zip_code, page))

    total_jobs = job_queue.qsize()
    log.info(
        "Enqueued %d jobs — %d sources × %d ZIPs × %d pages",
        total_jobs, len(ALL_SCRAPERS), len(zips), PAGES_PER_SOURCE_ZIP,
    )

    result_queue: asyncio.Queue = asyncio.Queue()
    source_semaphores = {
        src: asyncio.Semaphore(limit)
        for src, limit in SOURCE_CONCURRENCY.items()
    }

    t0 = time.monotonic()

    # Spawn workers + processor concurrently
    worker_tasks = [
        asyncio.create_task(
            worker(i + 1, job_queue, result_queue, source_semaphores, stop_event)
        )
        for i in range(workers)
    ]
    processor_task = asyncio.create_task(
        result_processor(result_queue, raw_store, qualified_writer, target, stop_event)
    )

    # Wait for queue to drain or stop_event
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    stop_event.set()
    qualified_count = await processor_task

    elapsed = time.monotonic() - t0
    total_raw = raw_store.count()
    raw_store.close()

    qualified_writer.flush_summary(total_jobs, total_raw)

    # POST to backend API
    if api_url:
        log.info("POSTing %d listings to %s ...", qualified_count, api_url)
        ingest_result = post_to_api(qualified_writer._listings, api_url=api_url)
        log.info(
            "Ingest complete — inserted=%d  updated=%d  skipped=%d",
            ingest_result.get("inserted", 0),
            ingest_result.get("updated", 0),
            ingest_result.get("skipped", 0),
        )

    log.info("=" * 60)
    log.info("Done in %.1fs", elapsed)
    log.info("Raw events stored : %d", total_raw)
    log.info("Qualified listings: %d / %d target", qualified_count, target)
    log.info("Output JSONL      : %s", OUT_DIR / "qualified_listings.jsonl")
    log.info("Summary JSON      : %s", OUT_DIR / "run_summary.json")
    log.info("=" * 60)

    # Print top 10 by yield
    top = sorted(
        qualified_writer._listings,
        key=lambda x: x.rent_to_price_pct or 0,
        reverse=True,
    )[:10]
    if top:
        log.info("\nTop 10 by rent/price yield:")
        log.info("%-40s  %10s  %8s  %6s  %s", "Address", "Price", "Rent/mo", "Yield%", "Phone")
        for l in top:
            log.info(
                "%-40s  $%9s  $%6s  %5.2f%%  %s",
                l.address[:40],
                f"{l.price:,}",
                f"{l.market_rent_est:,}" if l.market_rent_est else "?",
                l.rent_to_price_pct or 0,
                l.agent_phone or "—",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Homely real estate scraper")
    parser.add_argument("--target", type=int, default=TARGET_QUALIFIED,
                        help=f"Qualified listings to collect (default: {TARGET_QUALIFIED})")
    parser.add_argument("--workers", type=int, default=CONCURRENCY,
                        help=f"Asyncio worker count (default: {CONCURRENCY})")
    parser.add_argument("--zips", type=str, default=",".join(TARGET_ZIPS),
                        help="Comma-separated ZIP codes to search")
    parser.add_argument("--api", type=str, default=DEFAULT_API_URL,
                        help=f"Backend ingest URL (default: {DEFAULT_API_URL}). Pass 'none' to skip.")
    args = parser.parse_args()

    zips = [z.strip() for z in args.zips.split(",") if z.strip()]
    api_url = None if args.api.lower() == "none" else args.api
    log.info("Starting Homely scraper — target=%d, workers=%d, zips=%s, api=%s",
             args.target, args.workers, zips, api_url or "disabled")

    asyncio.run(run(args.target, args.workers, zips, api_url))


if __name__ == "__main__":
    main()
