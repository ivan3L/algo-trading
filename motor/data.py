"""Datos de mercado vía REST de Alpaca (feed IEX en tiempo real, gratis). Todo se devuelve en hora de Nueva York."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from .clock import ET, UTC, at, now_et

COLS = ["open", "high", "low", "close", "volume", "vwap"]


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    ts: datetime

    @property
    def mid(self) -> float: return (self.bid + self.ask) / 2.0
    @property
    def spread_bps(self) -> float: return 0.0 if self.mid <= 0 else (self.ask - self.bid) / self.mid * 1e4
    @property
    def latency_s(self) -> float: return max(0.0, (datetime.now(tz=UTC) - self.ts).total_seconds())


class MarketData:
    def __init__(self, key: str, secret: str):
        self.client = StockHistoricalDataClient(key, secret)

    def _bars(self, symbol: str, tf: TimeFrame, start: datetime, end: datetime | None, feed: DataFeed) -> pd.DataFrame:
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start.astimezone(UTC), end=end.astimezone(UTC) if end else None, feed=feed)
        df = self.client.get_stock_bars(req).df
        if df.empty: return pd.DataFrame(columns=COLS)
        if isinstance(df.index, pd.MultiIndex): df = df.xs(symbol, level="symbol")
        df = df.copy()
        df.index = pd.DatetimeIndex(df.index).tz_convert(ET)
        for c in COLS:
            if c not in df.columns: df[c] = 0.0
        return df[COLS].astype(float)

    def minute_bars(self, symbol: str, day: date, end: datetime | None = None) -> pd.DataFrame:
        """Barras de 1 minuto de la sesión regular de `day` hasta `end` (por defecto, ahora). IEX en tiempo real."""
        return self._bars(symbol, TimeFrame.Minute, at(day, "09:30"), end or now_et(), DataFeed.IEX)

    def history_minute_bars(self, symbol: str, n_days: int, before: date) -> list[pd.DataFrame]:
        """Barras de 1 minuto de sesión regular de los `n_days` días de mercado anteriores a `before` (SIP, > 15 min de antigüedad)."""
        start = at(before - timedelta(days=int(n_days * 1.8) + 5), "09:30")
        end = at(before, "00:00")
        df = self._bars(symbol, TimeFrame.Minute, start, end, DataFeed.SIP)
        if df.empty: return []
        df = df[[(t.time() >= at(before, "09:30").time()) and (t.time() < at(before, "16:00").time()) for t in df.index]]
        days = sorted({t.date() for t in df.index})[-n_days:]
        return [df[[t.date() == d for t in df.index]] for d in days]

    def prev_close(self, symbol: str, day: date) -> float | None:
        start = at(day - timedelta(days=10), "00:00"); end = at(day, "00:00")
        df = self._bars(symbol, TimeFrame.Day, start, end, DataFeed.SIP)
        return None if df.empty else float(df["close"].iloc[-1])

    def daily_close(self, symbol: str, day: date) -> float | None:
        """Cierre diario oficial (SIP) de `day`; disponible tras el cierre + 15 min."""
        df = self._bars(symbol, TimeFrame.Day, at(day, "00:00"), at(day + timedelta(days=1), "00:00"), DataFeed.SIP)
        return None if df.empty else float(df["close"].iloc[-1])

    def latest_quote(self, symbol: str) -> Quote:
        q = self.client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX))[symbol]
        ts = q.timestamp if q.timestamp.tzinfo else q.timestamp.replace(tzinfo=UTC)
        return Quote(symbol, float(q.bid_price), float(q.ask_price), ts)
