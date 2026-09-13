"""Tiempo de mercado: todo en America/New_York de forma explícita."""
from __future__ import annotations
import time as _time
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def now_et() -> datetime:
    return datetime.now(tz=ET)


def parse_hms(s: str) -> time:
    parts = [int(p) for p in s.split(":")]
    while len(parts) < 3: parts.append(0)
    return time(*parts)


def at(d: date, hms: str | time) -> datetime:
    t = parse_hms(hms) if isinstance(hms, str) else hms
    return datetime.combine(d, t, tzinfo=ET)


def sleep_until(target: datetime, poll_s: float = 0.25) -> None:
    while True:
        remaining = (target - now_et()).total_seconds()
        if remaining <= 0: return
        _time.sleep(min(remaining, poll_s if remaining < 5 else 5.0))


def first_of_next_month(d: date) -> date:
    return date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)


def check_key(strategy: str, d: date, hms: str) -> str:
    """Clave idempotente de una revisión programada."""
    return f"{strategy}|{d.isoformat()}|{hms}"


def order_key(strategy: str, d: date, symbol: str, side: str, seq: int, version: str) -> str:
    """client_order_id determinista (Alpaca rechaza duplicados con 422, que es lo que queremos)."""
    return f"{strategy}-{d.strftime('%Y%m%d')}-{symbol}-{side}-{seq}-{version}"[:48]
