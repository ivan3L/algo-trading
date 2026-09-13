"""Prueba de extremo a extremo del orquestador con un broker y datos falsos: sin red, sin Alpaca."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
import pytest
from alpaca.trading.enums import OrderStatus
from motor import journal, risk, session as sess
from motor.clock import ET, at
from motor.data import Quote
from motor.execution import Fill
from tests.conftest import make_bars

DAY = date(2026, 9, 14)


def full_day(closes_by_time: dict[str, float], base: float) -> "pd.DataFrame":
    """Serie de 391 cierres de 1 min (9:30–16:00) por tramos: {'09:35': 101, '10:00': 99, ...} → escalones."""
    closes, cur, t = [], base, datetime.combine(DAY, time(9, 30), tzinfo=ET)
    marks = sorted((at(DAY, k), v) for k, v in closes_by_time.items())
    for i in range(391):
        for when, v in marks:
            if t >= when: cur = v
        closes.append(cur); t += timedelta(minutes=1)
    return make_bars(closes)


class FakeData:
    def __init__(self):
        # QQQ: sube a 101 en la primera barra de 5 min (S1 alcista), cae a 99 antes de las 10:00 (S3 rebote)
        self.today = {"QQQ": full_day({"09:31": 101.0, "09:45": 99.0}, 100.0),
                      # SPY: rompe la banda al alza a las 10:00 (101 > 100,5) y vuelve dentro a las 10:30
                      "SPY": full_day({"09:50": 101.0, "10:20": 100.2}, 100.0)}
        self.px = {"TQQQ": 80.0, "SQQQ": 25.0, "SPY": 101.0, "SH": 36.0, "QQQ": 99.0, "PSQ": 33.0}

    def minute_bars(self, symbol, day, end=None):
        df = self.today[symbol]
        return df[df.index < end] if end is not None else df

    def history_minute_bars(self, symbol, n, before):
        move = 0.004 if symbol == "QQQ" else 0.005
        return [make_bars([100.0] * 5 + [100.0 * (1 + (1 if i % 2 else -1) * move)] * 386) for i in range(n)]

    def prev_close(self, symbol, day): return 100.0
    def daily_close(self, symbol, day): return 100.0
    def latest_quote(self, symbol):
        p = self.px[symbol]; return Quote(symbol, p - 0.01, p + 0.01, datetime.now(tz=ET))


@dataclass
class FakeOrder:
    id: str; symbol: str; qty: float; status: OrderStatus = OrderStatus.NEW
    limit_price: float | None = None; stop_price: float | None = None
    filled_qty: float = 0.0; filled_avg_price: float = 0.0; filled_at: datetime | None = None; client_order_id: str = ""


class FakeBroker:
    def __init__(self, clock):
        self.clock, self.orders, self.pos, self.n = clock, {}, {}, 0
        self.stop_hits_after = {}  # símbolo -> hora ET a partir de la cual el stop "salta"

    def _new(self, symbol, qty, coid, **kw):
        self.n += 1; o = FakeOrder(id=f"o{self.n}", symbol=symbol, qty=qty, client_order_id=coid, **kw); self.orders[o.id] = o; return o

    def calendar(self, day): return SimpleNamespace(date=day, open=at(day, "09:30"), close=at(day, "16:00"))
    def account_equity(self): return 100_000.0
    def positions(self): return {k: v for k, v in self.pos.items() if v > 0}
    def open_orders(self): return [o for o in self.orders.values() if o.status in (OrderStatus.NEW, OrderStatus.ACCEPTED)]
    def order_by_coid(self, coid): return next((o for o in self.orders.values() if o.client_order_id == coid), None)

    def order(self, oid):
        o = self.orders[oid]
        hit = self.stop_hits_after.get(o.symbol)
        if o.stop_price and o.status == OrderStatus.NEW and hit and self.clock() >= hit:
            o.status, o.filled_qty, o.filled_avg_price = OrderStatus.FILLED, o.qty, o.stop_price
            self.pos[o.symbol] = self.pos.get(o.symbol, 0) - o.qty
        return o

    def buy_marketable_limit(self, symbol, qty, ask, offset_bps, coid):
        return self.order_by_coid(coid) or self._new(symbol, qty, coid, limit_price=round(ask * (1 + offset_bps / 1e4), 2))
    def sell_market(self, symbol, qty, coid):
        return self.order_by_coid(coid) or self._new(symbol, qty, coid)
    def place_stop(self, symbol, qty, stop_price, coid):
        return self.order_by_coid(coid) or self._new(symbol, qty, coid, stop_price=round(stop_price, 2))
    def replace_stop(self, oid, stop_price): self.orders[oid].stop_price = round(stop_price, 2)
    def cancel(self, oid): self.orders[oid].status = OrderStatus.CANCELED
    def cancel_all_for(self, symbol):
        for o in self.open_orders():
            if o.symbol == symbol: self.cancel(o.id)

    def wait_fill(self, oid, timeout_s, poll_s=1.0):
        o = self.orders[oid]
        if o.stop_price: return None
        px = o.limit_price if o.limit_price else {"TQQQ": 80.0, "SQQQ": 25.0, "SPY": 101.0, "SH": 36.0, "QQQ": 99.0, "PSQ": 33.0}[o.symbol]
        o.status, o.filled_qty, o.filled_avg_price, o.filled_at = OrderStatus.FILLED, o.qty, px, self.clock()
        self.pos[o.symbol] = self.pos.get(o.symbol, 0) + (o.qty if o.limit_price else -o.qty)
        return Fill(oid, o.symbol, o.qty, px, o.filled_at)


@pytest.fixture
def world(tmp_path, monkeypatch, cfg):
    clock = {"now": at(DAY, "09:20")}
    monkeypatch.setattr(sess, "now_et", lambda: clock["now"])
    monkeypatch.setattr(sess, "sleep_until", lambda target, poll_s=0.25: clock.__setitem__("now", max(clock["now"], target)))
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(journal, "now_et", lambda: clock["now"])
    monkeypatch.setattr(risk.State, "save", lambda self, path=None: risk.State.__dict__["save"].__wrapped__(self, tmp_path / "state.json") if hasattr(risk.State.__dict__["save"], "__wrapped__") else None)
    broker = FakeBroker(lambda: clock["now"])
    return SimpleNamespace(clock=clock, broker=broker, data=FakeData(), state=risk.State(), cfg=cfg)


def test_ventana_manana_y_tarde(world):
    w = world
    w.broker.stop_hits_after["TQQQ"] = at(DAY, "10:45")  # el stop de S1 salta en el servidor a las 10:45
    s = sess.Session("morning", w.cfg, w.broker, w.data, w.state)
    summary = s.run()
    ev = journal.read_day(DAY)
    types = [e["type"] for e in ev]
    entries = [e for e in ev if e["type"] == "entry"]
    exits = [e for e in ev if e["type"] == "exit"]
    # S1 entra en TQQQ a las 9:35, S3 en QQQ a las 10:00, S2 en SPY a las 10:00
    assert sorted(e["strategy"] for e in entries) == ["S1", "S2", "S3"]
    s1 = next(e for e in entries if e["strategy"] == "S1"); assert s1["symbol"] == "TQQQ" and s1["qty"] > 0 and s1["stop_price"] < s1["entry_price"]
    assert next(e for e in entries if e["strategy"] == "S3")["symbol"] == "QQQ"
    assert next(e for e in entries if e["strategy"] == "S2")["symbol"] == "SPY"
    # S2 sale por señal a las 10:30 (precio vuelve dentro de la banda); S1 sale por stop detectado en la siguiente revisión
    assert {(e["strategy"], e["source"]) for e in exits} == {("S2", "signal"), ("S1", "stop")}
    s1x = next(e for e in exits if e["strategy"] == "S1"); assert s1x["exit_price"] == pytest.approx(s1["stop_price"], abs=0.01)
    # el P&L contabilizado es el neto a 10 pb (el más conservador) y es menor que el bruto
    assert s1x["pnl_booked"] == pytest.approx(s1x["net_10bps"]) and s1x["pnl_booked"] < s1x["pnl_gross"]
    # S3 sigue abierta al cerrar la ventana de mañana; no hay incidentes
    assert w.state.books["S3"].open_symbol == "QQQ" and summary["incidents"] == 0
    assert w.broker.positions() == {"QQQ": w.state.books["S3"].open_qty}
    n_before = len(ev)

    # relanzar la mañana no repite nada (idempotencia por clave)
    w.clock["now"] = at(DAY, "09:20")
    sess.Session("morning", w.cfg, w.broker, w.data, w.state).run()
    ev2 = journal.read_day(DAY)
    assert len([e for e in ev2 if e["type"] == "entry"]) == 3 and len(ev2) == n_before + 3  # solo session_start, reconcile y session_end nuevos

    # tarde: cierre de todo a las 15:55 y marcas de fin de día
    w.clock["now"] = at(DAY, "12:20")
    summary = sess.Session("afternoon", w.cfg, w.broker, w.data, w.state).run()
    ev3 = journal.read_day(DAY)
    s3x = [e for e in ev3 if e["type"] == "exit" and e["strategy"] == "S3"]
    assert len(s3x) == 1 and s3x[0]["source"] == "eod"
    assert w.broker.positions() == {} and all(b.open_symbol is None for b in w.state.books.values())
    assert {e["strategy"] for e in ev3 if e["type"] == "eod_mark"} == {"S1", "S2", "S3"}
    assert summary.get("spy_close") == pytest.approx(100.2)
    # los libros reflejan el P&L neto acumulado
    for k, b in w.state.books.items():
        booked = sum(e["pnl_booked"] for e in ev3 if e["type"] == "exit" and e["strategy"] == k)
        assert b.equity == pytest.approx(10_000 + booked)


def test_reconciliacion_bloquea_entradas(world):
    w = world
    w.broker.pos["TQQQ"] = 5  # posición que el estado no conoce
    s = sess.Session("morning", w.cfg, w.broker, w.data, w.state)
    s.run()
    ev = journal.read_day(DAY)
    assert any(e["type"] == "incident" and "reconciliación" in e["msg"] for e in ev)
    assert not [e for e in ev if e["type"] == "entry"]


def test_media_sesion_no_opera(world, monkeypatch):
    w = world
    monkeypatch.setattr(w.broker, "calendar", lambda day: SimpleNamespace(date=day, open=at(day, "09:30"), close=at(day, "13:00")))
    out = sess.Session("morning", w.cfg, w.broker, w.data, w.state).run()
    assert "media sesión" in out["skipped"]
