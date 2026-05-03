from __future__ import annotations
import logging
from typing import Optional
import httpx
from ..config import TELEGRAM_BOT_TOKEN

log = logging.getLogger(__name__)
API = "https://api.telegram.org"


def _url(method: str) -> str:
    return f"{API}/bot{TELEGRAM_BOT_TOKEN}/{method}"


async def send_message(chat_id: str | int, text: str, parse_mode: str = "HTML") -> bool:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set; skipping send_message")
        return False
    if not chat_id:
        log.warning("No chat_id; skipping send_message")
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            _url("sendMessage"),
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True},
        )
    if r.status_code != 200:
        log.error("Telegram sendMessage failed: %s %s", r.status_code, r.text)
        return False
    return True


async def get_updates(offset: int | None = None, timeout: int = 25) -> list[dict]:
    if not TELEGRAM_BOT_TOKEN:
        return []
    params: dict = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    async with httpx.AsyncClient(timeout=timeout + 5) as client:
        r = await client.get(_url("getUpdates"), params=params)
    if r.status_code != 200:
        log.error("Telegram getUpdates failed: %s %s", r.status_code, r.text)
        return []
    return r.json().get("result", [])
