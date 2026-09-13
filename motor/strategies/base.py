"""Tipos comunes a las estrategias. Las estrategias son funciones puras sobre DataFrames de barras de 1 minuto
(índice: DatetimeIndex en America/New_York; columnas: open, high, low, close, volume, vwap)."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any
import pandas as pd


@dataclass
class Decision:
    strategy: str
    action: str                       # "enter" | "exit" | "hold" | "skip"
    symbol: str | None = None         # ETF a comprar (enter) o mantenido (exit/hold)
    stop_pct: float | None = None     # distancia al stop como fracción del precio de entrada del ETF ejecutado
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_enter(self) -> bool: return self.action == "enter"


def bars_until(df: pd.DataFrame, t: time) -> pd.DataFrame:
    """Barras cuyo inicio es anterior o igual a la hora t (hora ET)."""
    if df.empty: return df
    return df[[ts.time() <= t for ts in df.index]]


def last_close_before(df: pd.DataFrame, t: time) -> float | None:
    sub = bars_until(df, t)
    return None if sub.empty else float(sub["close"].iloc[-1])


def session_vwap(df: pd.DataFrame) -> float | None:
    """VWAP de la sesión a partir del vwap por barra ponderado por volumen (o del cierre si no hay vwap)."""
    if df.empty: return None
    vol = df["volume"].astype(float)
    px = df["vwap"].astype(float) if "vwap" in df.columns else df["close"].astype(float)
    if vol.sum() <= 0: return float(px.iloc[-1])
    return float((px * vol).sum() / vol.sum())
