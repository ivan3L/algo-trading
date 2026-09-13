"""S2 · Banda de ruido intradía sobre SPY (inspirada en Zarattini, Barbon y Aziz, 2024).
Banda: [min(apertura, cierre previo)·(1−σ_t), max(apertura, cierre previo)·(1+σ_t)], con σ_t la media a N días
del movimiento absoluto apertura→t. Entrada al salir de la banda del lado del VWAP; la banda actúa de stop."""
from __future__ import annotations
from datetime import time
from statistics import fmean
import pandas as pd
from ..config import StrategyConfig
from .base import Decision, last_close_before, session_vwap, bars_until

MIN_STOP_PCT = 0.001  # 10 pb: evita tamaños absurdos cuando el precio está justo en la banda


def sigma_by_time(history: list[pd.DataFrame], mark: time) -> float | None:
    moves = []
    for df in history:
        if df.empty: continue
        o = float(df["open"].iloc[0])
        px = last_close_before(df, mark)
        if px is not None and o > 0: moves.append(abs(px / o - 1.0))
    return fmean(moves) if moves else None


def band(today: pd.DataFrame, prev_close: float, sigma: float) -> tuple[float, float]:
    o = float(today["open"].iloc[0])
    return min(o, prev_close) * (1.0 - sigma), max(o, prev_close) * (1.0 + sigma)


def decide(today: pd.DataFrame, prev_close: float, sigma: float | None, mark: time,
           in_position: str | None, cfg: StrategyConfig) -> Decision:
    if today.empty or sigma is None or sigma <= 0:
        return Decision(cfg.key, "skip", reason="sin barras o sin σ")
    sub = bars_until(today, mark)
    px = last_close_before(today, mark)
    vwap = session_vwap(sub)
    if px is None or vwap is None:
        return Decision(cfg.key, "skip", reason="sin precio a la hora de revisión")
    lower, upper = band(today, prev_close, sigma)
    meta = {"px": px, "vwap": vwap, "lower": lower, "upper": upper, "sigma": sigma, "mark": mark.isoformat()}
    if in_position == cfg.long_symbol:
        if px < upper: return Decision(cfg.key, "exit", symbol=in_position, reason="precio vuelve dentro de la banda", meta=meta)
        return Decision(cfg.key, "hold", symbol=in_position, stop_pct=max((px - upper) / px, MIN_STOP_PCT), reason="mantener, stop en banda superior", meta=meta)
    if in_position == cfg.short_symbol:
        if px > lower: return Decision(cfg.key, "exit", symbol=in_position, reason="precio vuelve dentro de la banda", meta=meta)
        return Decision(cfg.key, "hold", symbol=in_position, stop_pct=max((lower - px) / px, MIN_STOP_PCT), reason="mantener, stop en banda inferior", meta=meta)
    if px > upper and px > vwap:
        return Decision(cfg.key, "enter", symbol=cfg.long_symbol, stop_pct=max((px - upper) / px, MIN_STOP_PCT) * cfg.leverage, reason="ruptura alcista de la banda sobre VWAP", meta=meta)
    if px < lower and px < vwap:
        return Decision(cfg.key, "enter", symbol=cfg.short_symbol, stop_pct=max((lower - px) / px, MIN_STOP_PCT) * cfg.leverage, reason="ruptura bajista de la banda bajo VWAP", meta=meta)
    return Decision(cfg.key, "skip", reason="dentro de la banda", meta=meta)
