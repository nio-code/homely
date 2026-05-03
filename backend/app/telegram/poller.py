"""Long-polls Telegram getUpdates and dispatches commands.

Commands:
  /start   — captures this chat's id; future pin notifications go here
  /list    — replies with the currently pinned listings
  /unpin <id>  — clears pinned_at for the given listing id
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional
from sqlmodel import Session, select
from ..config import TELEGRAM_BOT_TOKEN
from ..db import engine
from ..models import Listing
from .client import get_updates, send_message
from .state import load, save, set_chat_id
from .notifier import format_pin_message

log = logging.getLogger(__name__)


def _pinned() -> list[Listing]:
    with Session(engine) as session:
        stmt = select(Listing).where(Listing.pinned_at.is_not(None)).order_by(Listing.pinned_at.desc())
        return session.exec(stmt).all()


def _unpin(listing_id: int) -> Listing | None:
    with Session(engine) as session:
        l = session.get(Listing, listing_id)
        if not l:
            return None
        l.pinned_at = None
        session.add(l)
        session.commit()
        session.refresh(l)
        return l


async def handle_message(msg: dict) -> None:
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    if text.startswith("/start"):
        set_chat_id(chat_id)
        await send_message(chat_id, "✅ Linked. Top picks will land here. Use /list and /unpin &lt;id&gt;.")
        return

    if text.startswith("/list"):
        rows = _pinned()
        if not rows:
            await send_message(chat_id, "No pinned listings.")
            return
        body = "\n\n".join(f"<b>#{r.id}</b>\n{format_pin_message(r)}" for r in rows[:5])
        await send_message(chat_id, f"📌 Pinned ({len(rows)}):\n\n{body}")
        return

    if text.startswith("/unpin"):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await send_message(chat_id, "Usage: /unpin &lt;id&gt;")
            return
        l = _unpin(int(parts[1]))
        if not l:
            await send_message(chat_id, f"Listing #{parts[1]} not found.")
        else:
            await send_message(chat_id, f"Unpinned #{l.id} — {l.address}.")
        return


async def run_poller(stop_event: asyncio.Event) -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set; poller idle.")
        await stop_event.wait()
        return

    state = load()
    offset = state.get("offset")
    log.info("Telegram poller starting (offset=%s)", offset)
    while not stop_event.is_set():
        try:
            updates = await get_updates(offset=offset, timeout=25)
            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message")
                if msg:
                    await handle_message(msg)
            if updates:
                state = load()
                state["offset"] = offset
                save(state)
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001
            log.exception("poller error: %s", e)
            await asyncio.sleep(2)
