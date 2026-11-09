"""Telegram notifications to the workshop's owner and masters about dangerous incidents.

When an incident is processed and is CRITICAL or tripped the safety layer ("Остановите станок"),
every owner and master of the workshop who has Telegram gets a short message, in their language,
except the person who reported it (they already have the card). Sent straight to the Telegram Bot
API with the bot's token (settings.telegram_bot_token, the same FIBO_TELEGRAM_BOT_TOKEN the bot
reads); without a token notifications are off. A failed send is logged and never breaks the pipeline.
Owners get Telegram by linking their web account to the bot (POST /auth/telegram-link).
"""

import html
import logging

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.db.base import IncidentLevel, Role
from app.db.session import SessionLocal
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.user import User

logger = logging.getLogger("fibo.notify")
TELEGRAM_API = "https://api.telegram.org"
TIMEOUT_S = 10.0
_transport: httpx.AsyncBaseTransport | None = None  # tests inject a MockTransport

TEXTS = {
    "ru": {
        "stop": "⛔ <b>Остановите станок · {machine}</b>",
        "critical": "🔴 <b>Критично · {machine}</b>",
        "from": "Сообщил: {who}",
        "link": "Карточка на сайте: {url}",
    },
    "kk": {
        "stop": "⛔ <b>Станокты тоқтатыңыз · {machine}</b>",
        "critical": "🔴 <b>Қауіпті · {machine}</b>",
        "from": "Хабарлаған: {who}",
        "link": "Сайттағы карточка: {url}",
    },
}


def should_notify(incident: Incident) -> bool:
    return bool(incident.safety_triggered) or incident.level == IncidentLevel.CRITICAL


def message_text(incident: Incident, machine: Machine, reporter: User | None, lang: str) -> str:
    t = TEXTS.get(lang, TEXTS["ru"])
    header = t["stop" if incident.safety_triggered else "critical"].format(machine=html.escape(machine.name))
    footer = [t["from"].format(who=html.escape(reporter.full_name))] if reporter is not None else []
    footer.append(t["link"].format(url=f"{settings.web_base_url.rstrip('/')}/app/machines/{machine.id}"))
    blocks = [header, html.escape(incident.verdict or ""), "\n".join(footer)]
    return "\n\n".join(b for b in blocks if b)


async def recipients(session, machine: Machine, reporter_id: int | None) -> list[User]:
    stmt = select(User).where(
        User.workshop_id == machine.workshop_id,
        User.role.in_([Role.OWNER, Role.MASTER]),
        User.telegram_id.is_not(None),
    )
    return [u for u in await session.scalars(stmt) if u.id != reporter_id]


async def _send(client: httpx.AsyncClient, chat_id: int, text: str) -> bool:
    url = f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        response = await client.post(url, json=body)
    except httpx.HTTPError as exc:
        logger.warning(
            "telegram notification failed", extra={"chat_id": chat_id, "error": type(exc).__name__}
        )
        return False
    if response.status_code != 200:  # e.g. 403: the person blocked the bot
        logger.warning(
            "telegram refused notification", extra={"chat_id": chat_id, "status": response.status_code}
        )
        return False
    return True


async def notify_incident(incident_id: int) -> int:
    """Send the alert for one processed incident; returns how many people got it. Never raises."""
    if not settings.telegram_bot_token:
        return 0
    try:
        async with SessionLocal() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None or not should_notify(incident):
                return 0
            machine = await session.get(Machine, incident.machine_id)
            reporter = await session.get(User, incident.user_id) if incident.user_id else None
            people = await recipients(session, machine, incident.user_id)
            messages = [
                (u.telegram_id, message_text(incident, machine, reporter, u.language)) for u in people
            ]
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=_transport) as client:
            sent = [await _send(client, chat_id, text) for chat_id, text in messages]
    except Exception:  # logged with traceback; the incident itself is already saved
        logger.exception("notifications failed", extra={"incident_id": incident_id})
        return 0
    logger.info("incident notifications", extra={"incident_id": incident_id, "sent": sum(sent)})
    return sum(sent)
