# Homely

Local real-estate dashboard + Telegram notifier. Browse listings on `localhost:8000`, click **Pin** on a listing → it lands in your Telegram with the agent's phone ready to dial.

Single-user, single-machine. Built to iterate on.

## Stack

- **Backend**: FastAPI + SQLModel + SQLite (`backend/`)
- **Frontend**: vanilla HTML/JS, served as static assets by FastAPI (no build step)
- **Telegram**: raw Bot HTTP API, long-poll for `/start`, `/list`, `/unpin` chat commands

## First-time setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# edit .env — paste TELEGRAM_BOT_TOKEN; chat_id is auto-captured on first /start
python -m app.seed
```

Requires Python 3.9+.

## Run

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Then open <http://localhost:8000>.

## Linking Telegram

1. Make sure `TELEGRAM_BOT_TOKEN` is set in `backend/.env`.
2. With the server running, message the bot in Telegram: `/start`.
3. The poller writes your `chat.id` to `backend/state.json`. Future pin notifications go there.

## Editing listings

Listings live in `backend/data/listings.json`. Re-run `python -m app.seed` to upsert (idempotent on `(source, source_id)`).

Schema:

```json
{
  "source": "coldwell_banker | compass | ...",
  "source_id": "stable id within that source",
  "address": "123 Main St",
  "city": "Irvine",
  "state": "CA",
  "zip": "92620",
  "price": 1998689,
  "beds": 4,
  "baths": 3,
  "sqft": 2400,
  "lot_sqft": null,
  "property_type": "Single Family",
  "listing_url": "https://...",
  "agent_name": "Jane Doe",
  "agent_phone": "(949) 555-1234",
  "agent_email": "jane@example.com",
  "notes": "any free-form notes"
}
```

## Bot commands

- `/start` — link your chat (run once)
- `/list` — show top-5 most-recently-pinned
- `/unpin <id>` — clear pin (no notification fired)

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | sanity |
| GET | `/api/listings?pinned=&min_price=&max_price=&beds=&zip=` | filtered list |
| GET | `/api/listings/{id}` | one listing |
| POST | `/api/listings/{id}/pin` | pin + send Telegram |
| DELETE | `/api/listings/{id}/pin` | unpin (silent) |

## What's deferred

- Scrapers (Coldwell Banker / Compass) — for now, edit `data/listings.json`.
- Auto-scoring — pinning is manual.
- Auth — localhost only.
