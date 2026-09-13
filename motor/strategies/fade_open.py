"""S3 · Contra-apertura (control de reversión a la media): si el movimiento 9:30→10:00 de QQQ supera k·σ, se apuesta
a la reversión con QQQ (tras una caída) o PSQ (tras una subida)."""
from __future__ import annotations
from datetime import time
from statistics import stdev
import pandas as pd
from ..config import StrategyConfig
from .base import Decision, last_close_before

MARK = time(9, 59)  # última barra de 1 min antes de las 10:00


def open_move(df: pd.DataFrame) -> float | None:
    if df.empty: return None
    o = float(df["open"].iloc[0]); px = last_close_before(df, MARK)
    return None if px is None or o <= 0 else px / o - 1.0


def decide(today: pd.DataFrame, history: list[pd.DataFrame], cfg: StrategyConfig) -> Decision:
    moves = [m for m in (open_move(d) for d in history) if m is not None]
    if len(moves) < 5: return Decision(cfg.key, "skip", reason=f"historial insuficiente ({len(moves)} días)")
    sigma = stdev(moves)
    m = open_move(today)
    if m is None or sigma <= 0: return Decision(cfg.key, "skip", reason="sin movimiento de apertura")
    k, ks = float(cfg.params.get("threshold_sigmas", 1.5)), float(cfg.params.get("stop_sigmas", 1.0))
    meta = {"move": m, "sigma": sigma, "threshold": k * sigma}
    stop_pct = ks * sigma * cfg.leverage
    if m <= -k * sigma:
        return Decision(cfg.key, "enter", symbol=cfg.long_symbol, stop_pct=stop_pct, reason=f"caída de apertura {m:.2%} > {k}σ, apuesta a rebote", meta=meta)
    if m >= k * sigma:
        return Decision(cfg.key, "enter", symbol=cfg.short_symbol, stop_pct=stop_pct, reason=f"subida de apertura {m:.2%} > {k}σ, apuesta a recorte", meta=meta)
    return Decision(cfg.key, "skip", reason="movimiento de apertura dentro de lo normal", meta=meta)
