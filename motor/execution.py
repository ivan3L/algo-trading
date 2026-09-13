"""Capa fina y defensiva sobre alpaca-py. Siempre paper salvo autorización explícita por variable de entorno."""
from __future__ import annotations
import os, time
from dataclasses import dataclass
from datetime import date, datetime
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (LimitOrderRequest, MarketOrderRequest, StopOrderRequest, ReplaceOrderRequest,
                                     GetOrdersRequest, GetCalendarRequest)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, OrderStatus
from alpaca.common.exceptions import APIError

TERMINAL = {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED, OrderStatus.DONE_FOR_DAY}


@dataclass
class Fill:
    order_id: str
    symbol: str
    qty: float
    avg_price: float
    filled_at: datetime | None


def _px(x: float) -> float:
    """Alpaca exige ≤ 2 decimales en precios ≥ 1 $ (alpaca-py 0.44 lo valida en cliente)."""
    return round(float(x), 2) if x >= 1 else round(float(x), 4)


class Broker:
    def __init__(self, key: str, secret: str, paper: bool = True):
        if not paper and os.environ.get("MOTOR_ALLOW_LIVE") != "yes":
            raise RuntimeError("Modo real bloqueado: este motor solo opera en paper (MOTOR_ALLOW_LIVE no autorizado).")
        self.paper = paper
        self.tc = TradingClient(key, secret, paper=paper)

    # --- lectura
    def account_equity(self) -> float:
        return float(self.tc.get_account().equity)

    def positions(self) -> dict[str, float]:
        return {p.symbol: float(p.qty) for p in self.tc.get_all_positions()}

    def open_orders(self) -> list:
        return list(self.tc.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=200)))

    def calendar(self, day: date):
        cal = self.tc.get_calendar(GetCalendarRequest(start=day, end=day))
        return cal[0] if cal else None

    def order(self, order_id: str):
        return self.tc.get_order_by_id(order_id)

    def order_by_coid(self, coid: str):
        try: return self.tc.get_order_by_client_id(coid)
        except APIError: return None

    # --- escritura
    def buy_marketable_limit(self, symbol: str, qty: int, ask: float, offset_bps: float, coid: str):
        existing = self.order_by_coid(coid)
        if existing is not None: return existing                      # idempotencia: ya se envió
        req = LimitOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                                limit_price=_px(ask * (1 + offset_bps / 1e4)), client_order_id=coid)
        return self.tc.submit_order(req)

    def sell_market(self, symbol: str, qty: float, coid: str):
        existing = self.order_by_coid(coid)
        if existing is not None: return existing
        req = MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY, client_order_id=coid)
        return self.tc.submit_order(req)

    def place_stop(self, symbol: str, qty: float, stop_price: float, coid: str):
        existing = self.order_by_coid(coid)
        if existing is not None: return existing
        req = StopOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                               stop_price=_px(stop_price), client_order_id=coid)
        return self.tc.submit_order(req)

    def replace_stop(self, order_id: str, stop_price: float):
        return self.tc.replace_order_by_id(order_id, ReplaceOrderRequest(stop_price=_px(stop_price)))

    def cancel(self, order_id: str) -> None:
        try: self.tc.cancel_order_by_id(order_id)
        except APIError: pass

    def cancel_all_for(self, symbol: str) -> int:
        n = 0
        for o in self.open_orders():
            if o.symbol == symbol: self.cancel(o.id); n += 1
        return n

    def wait_fill(self, order_id: str, timeout_s: float, poll_s: float = 1.0) -> Fill | None:
        """Espera a que la orden termine. Si no se ejecuta en el plazo, la cancela y devuelve None (o el parcial)."""
        t0 = time.time()
        while True:
            o = self.order(order_id)
            if o.status in TERMINAL or time.time() - t0 > timeout_s:
                if o.status not in TERMINAL:
                    self.cancel(order_id); time.sleep(1.0); o = self.order(order_id)
                fq = float(o.filled_qty or 0)
                if fq > 0:
                    return Fill(str(o.id), o.symbol, fq, float(o.filled_avg_price), o.filled_at)
                return None
            time.sleep(poll_s)
