import pandas as pd
import pytest
from datetime import date, datetime, timedelta
from motor.clock import ET
from motor import config as cfgmod

DAY = date(2026, 9, 14)  # lunes


def make_bars(closes, day=DAY, start="09:30", spread=0.05, volume=1000):
    """Barras de 1 minuto sintéticas: open = cierre anterior, high/low = ±spread."""
    h, m = (int(x) for x in start.split(":"))
    t0 = datetime(day.year, day.month, day.day, h, m, tzinfo=ET)
    rows, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = prev
        rows.append({"open": o, "high": max(o, c) + spread, "low": min(o, c) - spread, "close": c, "volume": volume, "vwap": (o + c) / 2})
        prev = c
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(closes))])
    return pd.DataFrame(rows, index=idx)


@pytest.fixture
def cfg():
    return cfgmod.load()
