"""S1 · Opening Range Breakout de 5 minutos (Zarattini y Aziz, 2023), versión largo-solo con ETF inverso."""
from __future__ import annotations
from datetime import date, timedelta
import pandas as pd
from ..clock import at
from ..config import StrategyConfig
from .base import Decision


def decide(bars_signal: pd.DataFrame, cfg: StrategyConfig, today: date) -> Decision:
    rm = int(cfg.params.get("range_minutes", 5))
    start, end = at(today, "09:30"), at(today, "09:30") + timedelta(minutes=rm)
    w = bars_signal[(bars_signal.index >= start) & (bars_signal.index < end)] if not bars_signal.empty else bars_signal
    if len(w) < rm:
        return Decision(cfg.key, "skip", reason=f"barras insuficientes en el rango de apertura ({len(w)}/{rm})")
    o, c = float(w["open"].iloc[0]), float(w["close"].iloc[-1])
    hi, lo = float(w["high"].max()), float(w["low"].min())
    meta = {"open": o, "close": c, "range_high": hi, "range_low": lo}
    if c > o:
        r = (c - lo) / c
        symbol = cfg.long_symbol
    elif c < o:
        r = (hi - c) / c
        symbol = cfg.short_symbol
    else:
        return Decision(cfg.key, "skip", reason="primera barra plana", meta=meta)
    if r <= 0:
        return Decision(cfg.key, "skip", reason="rango degenerado", meta=meta)
    return Decision(cfg.key, "enter", symbol=symbol, stop_pct=r * cfg.leverage,
                    reason=f"ruptura {'alcista' if symbol == cfg.long_symbol else 'bajista'}, R={r:.4%}", meta=meta)
