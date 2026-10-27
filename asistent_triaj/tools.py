"""Cele 3 tool-uri FIXE pe care le va putea apela agentul LLM.

LLM-ul nu scrie SQL: alege un tool și îi dă parametri, iar aici parametrii sunt validați
și transformați în interogări SQLAlchemy construite de noi. Rezultatul e mereu un dict/listă
simplă (poate fi transformat în JSON).
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from asistent_triaj.db import SecurityEvent

VALID_EVENT_IDS = (4624, 4625)
MAX_HOURS = 24 * 7
MAX_LIMIT = 50


class ToolError(ValueError):
    """Parametri invalizi primiți de un tool (mesajul e pentru LLM și pentru utilizator)."""


def _check_hours(hours) -> int:
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= MAX_HOURS:
        raise ToolError(f"hours trebuie să fie un număr întreg între 1 și {MAX_HOURS}")
    return hours


def _check_limit(limit) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ToolError(f"limit trebuie să fie un număr întreg între 1 și {MAX_LIMIT}")
    return limit


def _check_event_id(event_id) -> int | None:
    if event_id is None:
        return None
    if event_id not in VALID_EVENT_IDS:
        raise ToolError(f"event_id trebuie să fie 4624 sau 4625, nu {event_id!r}")
    return event_id


def search_events(session: Session, now: datetime, hours: int = 24, event_id: int | None = None,
                  username: str | None = None, source_ip: str | None = None,
                  limit: int = 20) -> dict:
    """Caută evenimente (cele mai recente primele) cu filtre opționale."""
    hours, limit, event_id = _check_hours(hours), _check_limit(limit), _check_event_id(event_id)
    since = now - timedelta(hours=hours)
    conditions = [SecurityEvent.timestamp >= since, SecurityEvent.timestamp <= now]
    if event_id is not None:
        conditions.append(SecurityEvent.event_id == event_id)
    if username:
        conditions.append(SecurityEvent.username == username)
    if source_ip:
        conditions.append(SecurityEvent.source_ip == source_ip)

    total = session.scalar(select(func.count()).select_from(SecurityEvent).where(*conditions))
    rows = session.scalars(
        select(SecurityEvent).where(*conditions)
        .order_by(SecurityEvent.timestamp.desc()).limit(limit)
    ).all()
    return {
        "total_matching": total,
        "returned": len(rows),
        "events": [
            {"timestamp": r.timestamp.isoformat(), "event_id": r.event_id, "username": r.username,
             "source_ip": r.source_ip, "workstation": r.workstation, "logon_type": r.logon_type}
            for r in rows
        ],
    }


def count_failures(session: Session, now: datetime, group_by: str, hours: int = 24,
                   limit: int = 10) -> dict:
    """Numără autentificările eșuate (4625), grupate pe IP sau pe utilizator."""
    hours, limit = _check_hours(hours), _check_limit(limit)
    columns = {"ip": SecurityEvent.source_ip, "user": SecurityEvent.username}
    if group_by not in columns:
        raise ToolError("group_by trebuie să fie 'ip' sau 'user'")
    col = columns[group_by]
    since = now - timedelta(hours=hours)
    rows = session.execute(
        select(col, func.count().label("failures"))
        .where(SecurityEvent.event_id == 4625,
               SecurityEvent.timestamp >= since, SecurityEvent.timestamp <= now)
        .group_by(col).order_by(func.count().desc(), col).limit(limit)
    ).all()
    return {"group_by": group_by, "hours": hours,
            "results": [{group_by: key, "failures": n} for key, n in rows]}


def top_ips(session: Session, now: datetime, hours: int = 24, event_id: int = 4625,
            limit: int = 5) -> dict:
    """Top adrese IP după numărul de evenimente, cu câți utilizatori diferiți au vizat."""
    hours, limit, event_id = _check_hours(hours), _check_limit(limit), _check_event_id(event_id)
    if event_id is None:
        raise ToolError("event_id este obligatoriu pentru top_ips")
    since = now - timedelta(hours=hours)
    rows = session.execute(
        select(SecurityEvent.source_ip, func.count().label("events"),
               func.count(func.distinct(SecurityEvent.username)).label("distinct_users"),
               func.min(SecurityEvent.timestamp), func.max(SecurityEvent.timestamp))
        .where(SecurityEvent.event_id == event_id,
               SecurityEvent.timestamp >= since, SecurityEvent.timestamp <= now)
        .group_by(SecurityEvent.source_ip)
        .order_by(func.count().desc(), SecurityEvent.source_ip).limit(limit)
    ).all()
    return {"event_id": event_id, "hours": hours, "results": [
        {"source_ip": ip, "events": n, "distinct_users": users,
         "first_seen": first.isoformat(), "last_seen": last.isoformat()}
        for ip, n, users, first, last in rows
    ]}


# Registrul de tool-uri: agentul (etapa 3) va apela tool-urile după nume.
TOOLS = {"search_events": search_events, "count_failures": count_failures, "top_ips": top_ips}
