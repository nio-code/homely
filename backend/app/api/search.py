"""Triggers the existing scraper module as a subprocess.

POST /api/search/run        — kick off `python -m scraper.main` in the background
GET  /api/search/status     — { running, started_at, finished_at, log_tail, last_inserted, last_updated }

Single-run-at-a-time guard. Output streamed to a tail buffer so the UI can show progress.
"""
from __future__ import annotations
import asyncio
import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/search", tags=["search"])

WORKSPACE = Path(__file__).resolve().parents[3]  # backend/app/api/search.py → workspace root
SCRAPER_CWD = WORKSPACE
LOG_TAIL_LINES = 50


class _State:
    proc: Optional[asyncio.subprocess.Process] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    returncode: Optional[int] = None
    log: deque = deque(maxlen=LOG_TAIL_LINES)
    inserted: int = 0
    updated: int = 0
    qualified: int = 0


_state = _State()


class RunRequest(BaseModel):
    target: int = 25
    zips: Optional[str] = None  # comma-separated; falls back to scraper default


class StatusResponse(BaseModel):
    running: bool
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    returncode: Optional[int]
    log_tail: list[str]
    inserted: int
    updated: int
    qualified: int


_INGEST_RE = re.compile(r"inserted=(\d+).*updated=(\d+)", re.IGNORECASE)
_QUALIFIED_RE = re.compile(r"QUALIFIED #")


async def _drain(stream: asyncio.StreamReader) -> None:
    while True:
        line = await stream.readline()
        if not line:
            return
        text = line.decode(errors="replace").rstrip()
        _state.log.append(text)
        if _QUALIFIED_RE.search(text):
            _state.qualified += 1
        m = _INGEST_RE.search(text)
        if m:
            _state.inserted = int(m.group(1))
            _state.updated = int(m.group(2))


async def _run_scraper(target: int, zips: Optional[str], api_key: str) -> None:
    cmd = [
        "python", "-m", "scraper.main",
        "--target", str(target),
        "--api", "http://localhost:8000/api/listings/ingest",
    ]
    if zips:
        cmd += ["--zips", zips]

    env = os.environ.copy()
    env["INGEST_API_KEY"] = api_key
    env["PYTHONUNBUFFERED"] = "1"

    _state.proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(SCRAPER_CWD),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _state.started_at = datetime.now(timezone.utc)
    _state.finished_at = None
    _state.returncode = None
    _state.log.clear()
    _state.inserted = 0
    _state.updated = 0
    _state.qualified = 0

    try:
        await _drain(_state.proc.stdout)  # stderr is merged into stdout
        _state.returncode = await _state.proc.wait()
    finally:
        _state.finished_at = datetime.now(timezone.utc)
        _state.proc = None


@router.post("/run", response_model=StatusResponse)
async def run_search(req: RunRequest) -> StatusResponse:
    if _state.proc is not None and _state.proc.returncode is None:
        raise HTTPException(409, "A search is already running")

    from ..config import INGEST_API_KEY
    if not INGEST_API_KEY:
        raise HTTPException(500, "INGEST_API_KEY not set in backend/.env")

    asyncio.create_task(_run_scraper(req.target, req.zips, INGEST_API_KEY))
    # Give the subprocess a moment to start so the first status poll has data
    await asyncio.sleep(0.1)
    return await status()


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    running = _state.proc is not None and _state.proc.returncode is None
    return StatusResponse(
        running=running,
        started_at=_state.started_at,
        finished_at=_state.finished_at,
        returncode=_state.returncode,
        log_tail=list(_state.log),
        inserted=_state.inserted,
        updated=_state.updated,
        qualified=_state.qualified,
    )
