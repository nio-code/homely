"""Persists chat_id and last update offset between runs."""
from __future__ import annotations
import json
from typing import Optional, Union
from ..config import STATE_FILE


def load() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_chat_id() -> Optional[str]:
    from ..config import TELEGRAM_CHAT_ID
    return TELEGRAM_CHAT_ID or load().get("chat_id")


def set_chat_id(chat_id: str | int) -> None:
    state = load()
    state["chat_id"] = str(chat_id)
    save(state)
