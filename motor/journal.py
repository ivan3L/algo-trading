"""Diario en JSONL: una línea por evento, un archivo por día. Fuente de verdad de las decisiones."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterator
from .clock import now_et
from .config import ROOT

JOURNAL_DIR = ROOT / "data" / "journal"


def _path(d: date) -> Path:
    return JOURNAL_DIR / f"{d.isoformat()}.jsonl"


def append(event: dict[str, Any], d: date | None = None) -> dict[str, Any]:
    d = d or now_et().date()
    event = {"ts": now_et().isoformat(timespec="milliseconds"), "date": d.isoformat(), **event}
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(_path(d), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def read_day(d: date) -> list[dict[str, Any]]:
    p = _path(d)
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def iter_all() -> Iterator[dict[str, Any]]:
    if not JOURNAL_DIR.exists(): return
    for p in sorted(JOURNAL_DIR.glob("*.jsonl")):
        for l in p.read_text(encoding="utf-8").splitlines():
            if l.strip(): yield json.loads(l)


def has_key(key: str, d: date) -> bool:
    return any(e.get("key") == key for e in read_day(d))
