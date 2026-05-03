import html
from ..models import Listing
from .client import send_message
from .state import get_chat_id


def _fmt_price(p: int) -> str:
    return f"${p:,}"


def _fmt_specs(l: Listing) -> str:
    parts = []
    if l.beds is not None:
        parts.append(f"{l.beds:g}bd")
    if l.baths is not None:
        parts.append(f"{l.baths:g}ba")
    if l.sqft:
        parts.append(f"{l.sqft:,} sqft")
    return " · ".join(parts)


def format_pin_message(l: Listing) -> str:
    addr = html.escape(f"{l.address}, {l.city} {l.state} {l.zip}")
    price = _fmt_price(l.price)
    specs = _fmt_specs(l)
    agent_name = html.escape(l.agent_name) if l.agent_name else ""
    phone = html.escape(l.agent_phone) if l.agent_phone else ""
    email = html.escape(l.agent_email) if l.agent_email else ""
    url = html.escape(l.listing_url)

    lines = [
        f"📍 <b>{addr}</b>",
        f"<b>{price}</b> · {specs}" if specs else f"<b>{price}</b>",
    ]
    agent_line = "Agent:"
    if agent_name:
        agent_line += f" {agent_name}"
    if phone:
        agent_line += f" — <a href='tel:{phone}'>{phone}</a>"
    if agent_name or phone:
        lines.append(agent_line)
    if email:
        lines.append(email)
    lines.append(f"🔗 <a href='{url}'>listing</a>")
    return "\n".join(lines)


async def send_pin(listing: Listing) -> bool:
    chat_id = get_chat_id()
    if not chat_id:
        return False
    return await send_message(chat_id, format_pin_message(listing))
