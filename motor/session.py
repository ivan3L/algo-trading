"""Orquestador de una ventana de sesión (mañana o tarde). Idempotente por clave de revisión; el estado se persiste
tras cada evento; los stops viven en el servidor de Alpaca, así que el proceso puede morir sin dejar riesgo huérfano."""
from __future__ import annotations
import traceback
from datetime import date, datetime, time, timedelta
from . import journal
from .clock import ET, at, now_et, sleep_until, check_key, order_key, parse_hms
from .config import Config, StrategyConfig
from .data import MarketData
from .execution import Broker
from .risk import State, Book, size_position
from .strategies import orb, noise_band, fade_open


class Session:
    def __init__(self, window: str, cfg: Config, broker: Broker, data: MarketData, state: State, version: str = "v1.0"):
        assert window in ("morning", "afternoon")
        self.window, self.cfg, self.broker, self.data, self.state, self.version = window, cfg, broker, data, state, version
        self.today: date = now_et().date()
        self.limits = cfg.limits
        self.trading_allowed = True
        self.incidents: list[str] = []
        self._hist: dict[str, list] = {}
        self._prev_close: dict[str, float] = {}
        self.universe = {sym for s in cfg.strategies() for sym in s.symbols}

    # ------------------------------------------------------------------ utilidades
    def log(self, **ev) -> None:
        journal.append(ev, self.today)

    def incident(self, msg: str, **extra) -> None:
        self.incidents.append(msg)
        self.log(type="incident", msg=msg, window=self.window, **extra)

    def book(self, s: StrategyConfig) -> Book:
        return self.state.book(s.key, float(self.cfg.account["book_equity_start"]))

    def hist(self, symbol: str, n: int) -> list:
        k = f"{symbol}:{n}"
        if k not in self._hist: self._hist[k] = self.data.history_minute_bars(symbol, n, self.today)
        return self._hist[k]

    def prev_close(self, symbol: str) -> float | None:
        if symbol not in self._prev_close:
            pc = self.data.prev_close(symbol, self.today)
            if pc is not None: self._prev_close[symbol] = pc
        return self._prev_close.get(symbol)

    # ------------------------------------------------------------------ calendario y reconciliación
    def market_open_today(self) -> tuple[bool, str]:
        cal = self.broker.calendar(self.today)
        if cal is None: return False, "mercado cerrado (sin sesión en el calendario)"
        close = getattr(cal, "close", None)
        close_t = close.time() if hasattr(close, "time") else parse_hms(str(close))
        if self.cfg.session.get("skip_half_days", True) and close_t != time(16, 0):
            return False, f"media sesión (cierre {close_t}); no se opera"
        return True, "ok"

    def reconcile(self) -> None:
        broker_pos = {k: v for k, v in self.broker.positions().items() if k in self.universe}
        expected = {b.open_symbol: float(b.open_qty) for b in self.state.books.values() if b.open_symbol}
        diffs = []
        for sym in set(broker_pos) | set(expected):
            if abs(broker_pos.get(sym, 0.0) - expected.get(sym, 0.0)) > 1e-9:
                diffs.append({"symbol": sym, "broker": broker_pos.get(sym, 0.0), "esperado": expected.get(sym, 0.0)})
        if diffs:
            self.trading_allowed = False
            self.incident("reconciliación: posiciones del broker ≠ esperadas; entradas bloqueadas", diffs=diffs)
        else:
            self.log(type="reconcile", window=self.window, ok=True, positions=broker_pos)

    # ------------------------------------------------------------------ ciclo de vida de una operación
    def try_enter(self, s: StrategyConfig, dec, key: str) -> None:
        b = self.book(s)
        ok, why = b.can_trade(self.today, s.max_trades_per_day)
        if not ok or not self.trading_allowed:
            self.log(type="skip", strategy=s.key, key=key, reason=why if not ok else "entradas bloqueadas por reconciliación", decision=dec.reason); return
        q = self.data.latest_quote(dec.symbol)
        if q.spread_bps > float(self.limits["max_spread_bps"]):
            self.log(type="skip", strategy=s.key, key=key, reason=f"spread {q.spread_bps:.1f} pb > límite", decision=dec.reason); return
        if q.latency_s > float(self.limits["max_data_latency_s"]):
            self.log(type="skip", strategy=s.key, key=key, reason=f"latencia de datos {q.latency_s:.1f} s > límite", decision=dec.reason); return
        qty = size_position(b.equity, q.ask, dec.stop_pct, float(self.limits["risk_per_trade"]), float(self.limits["max_notional_frac"]))
        if qty <= 0:
            self.log(type="skip", strategy=s.key, key=key, reason="tamaño calculado 0", decision=dec.reason); return
        seq = b.n_trades + 1
        coid = order_key(s.key, self.today, dec.symbol, "BUY", seq, self.version)
        self.state.count_order(self.today, int(self.limits["max_orders_per_session"]))
        signal_ts = now_et()
        order = self.broker.buy_marketable_limit(dec.symbol, qty, q.ask, float(self.limits["entry_limit_offset_bps"]), coid)
        self.log(type="order", strategy=s.key, key=key, trade_id=coid, symbol=dec.symbol, qty=qty, side="BUY",
                 limit_price=float(order.limit_price or 0), arrival_mid=q.mid, ask=q.ask, spread_bps=q.spread_bps, latency_s=q.latency_s)
        fill = self.broker.wait_fill(str(order.id), float(self.limits["entry_timeout_s"]))
        if fill is None:
            self.log(type="no_fill", strategy=s.key, key=key, trade_id=coid, symbol=dec.symbol, reason="sin ejecución en el plazo; cancelada"); return
        stop_price = fill.avg_price * (1.0 - dec.stop_pct)
        self.state.count_order(self.today, int(self.limits["max_orders_per_session"]))
        stop = self.broker.place_stop(dec.symbol, fill.qty, stop_price, order_key(s.key, self.today, dec.symbol, "STOP", seq, self.version))
        b.open_symbol, b.open_qty, b.open_entry_price, b.open_stop_order_id = dec.symbol, int(fill.qty), fill.avg_price, str(stop.id)
        b.trades_today += 1
        delay_bps = (fill.avg_price / q.mid - 1.0) * 1e4 if q.mid > 0 else 0.0
        self.log(type="entry", strategy=s.key, key=key, trade_id=coid, symbol=dec.symbol, qty=int(fill.qty), entry_price=fill.avg_price,
                 arrival_mid=q.mid, delay_bps=delay_bps, stop_price=round(stop_price, 4), stop_pct=dec.stop_pct, stop_order_id=str(stop.id),
                 reason=dec.reason, meta=dec.meta, signal_ts=signal_ts.isoformat(), fill_ts=str(fill.filled_at), book_equity=b.equity)
        self.state.save()

    def record_close(self, b: Book, exit_price: float, reason: str, source: str) -> None:
        qty, entry = b.open_qty, b.open_entry_price
        gross = (exit_price - entry) * qty
        nets = {}
        for bps in self.limits["synthetic_slippage_bps"]:
            cost = bps / 1e4 * (entry * qty + exit_price * qty)
            nets[f"net_{int(bps)}bps"] = gross - cost
        booked = nets[f"net_{int(max(self.limits['synthetic_slippage_bps']))}bps"]
        fired = b.apply_pnl(booked, self.today, self.limits)
        trade_id = order_key(b.strategy, date.fromisoformat(b.today) if b.today else self.today, b.open_symbol, "BUY", b.n_trades, self.version)
        self.log(type="exit", strategy=b.strategy, trade_id=trade_id, symbol=b.open_symbol, qty=qty, entry_price=entry, exit_price=exit_price,
                 pnl_gross=gross, **nets, pnl_booked=booked, reason=reason, source=source, limits_fired=fired, book_equity=b.equity)
        for f in fired: self.incident(f"{b.strategy}: {f}")
        b.open_symbol, b.open_qty, b.open_entry_price, b.open_stop_order_id = None, 0, 0.0, None
        self.state.save()

    def exit_position(self, b: Book, reason: str, source: str) -> None:
        if not b.open_symbol: return
        self.broker.cancel_all_for(b.open_symbol)
        coid = order_key(b.strategy, self.today, b.open_symbol, "SELL", b.n_trades + 1, self.version)
        self.state.count_order(self.today, int(self.limits["max_orders_per_session"]))
        order = self.broker.sell_market(b.open_symbol, b.open_qty, coid)
        fill = self.broker.wait_fill(str(order.id), 45.0)
        if fill is None:
            self.incident(f"{b.strategy}: la venta de {b.open_symbol} no se ejecutó; posición posiblemente abierta", symbol=b.open_symbol); return
        self.record_close(b, fill.avg_price, reason, source)

    def sync_stops(self) -> None:
        """Detecta stops ejecutados en el servidor desde la última revisión."""
        for b in self.state.books.values():
            if not b.open_symbol or not b.open_stop_order_id: continue
            try:
                o = self.broker.order(b.open_stop_order_id)
            except Exception as e:  # noqa: BLE001
                self.incident(f"{b.strategy}: no se pudo consultar el stop {b.open_stop_order_id}: {e}"); continue
            status = str(getattr(o.status, "value", o.status)).lower()
            if status == "filled" and float(o.filled_qty or 0) >= b.open_qty:
                self.record_close(b, float(o.filled_avg_price), "stop ejecutado en el servidor", "stop")
            elif status in ("canceled", "expired", "rejected"):
                self.incident(f"{b.strategy}: el stop de {b.open_symbol} está {o.status}; posición sin protección", symbol=b.open_symbol)
                self.exit_position(b, "stop perdido; cierre defensivo", "defensive")

    # ------------------------------------------------------------------ revisiones por estrategia
    def check_s1(self, s: StrategyConfig, key: str) -> None:
        bars = None
        for _ in range(6):  # la barra 9:34 puede tardar unos segundos en consolidarse
            bars = self.data.minute_bars(s.signal_symbol, self.today, at(self.today, "09:35"))
            if len(bars) >= int(s.params["range_minutes"]): break
            sleep_until(now_et() + timedelta(seconds=5))
        dec = orb.decide(bars, s, self.today)
        self.log(type="check", strategy=s.key, key=key, action=dec.action, reason=dec.reason, meta=dec.meta)
        if dec.is_enter: self.try_enter(s, dec, key)

    def check_s3(self, s: StrategyConfig, key: str) -> None:
        bars = self.data.minute_bars(s.signal_symbol, self.today, at(self.today, "10:00"))
        dec = fade_open.decide(bars, self.hist(s.signal_symbol, int(s.params["lookback_days"])), s)
        self.log(type="check", strategy=s.key, key=key, action=dec.action, reason=dec.reason, meta=dec.meta)
        if dec.is_enter: self.try_enter(s, dec, key)

    def check_s2(self, s: StrategyConfig, key: str, mark: time) -> None:
        b = self.book(s)
        bars = self.data.minute_bars(s.signal_symbol, self.today, at(self.today, mark))
        pc = self.prev_close(s.signal_symbol)
        sigma = noise_band.sigma_by_time(self.hist(s.signal_symbol, int(s.params["lookback_days"])), mark)
        if pc is None:
            self.log(type="check", strategy=s.key, key=key, action="skip", reason="sin cierre previo"); return
        dec = noise_band.decide(bars, pc, sigma, mark, b.open_symbol, s)
        self.log(type="check", strategy=s.key, key=key, action=dec.action, reason=dec.reason, meta=dec.meta)
        if dec.is_enter: self.try_enter(s, dec, key)
        elif dec.action == "exit": self.exit_position(b, dec.reason, "signal")
        elif dec.action == "hold" and b.open_stop_order_id and dec.stop_pct:
            # la banda actúa de stop trailing: el stop se mueve a la banda vigente (solo se acerca, nunca se aleja)
            px = float(bars["close"].iloc[-1]); new_stop = px * (1.0 - dec.stop_pct)
            try:
                o = self.broker.order(b.open_stop_order_id)
                if new_stop > float(o.stop_price or 0):
                    self.broker.replace_stop(b.open_stop_order_id, new_stop)
                    self.log(type="stop_update", strategy=s.key, key=key, symbol=b.open_symbol, stop_price=round(new_stop, 4))
            except Exception as e:  # noqa: BLE001
                self.incident(f"{s.key}: no se pudo mover el stop: {e}")

    def eod_close(self, key: str) -> None:
        for b in self.state.books.values():
            if b.open_symbol: self.exit_position(b, "cierre de sesión 15:55", "eod")
        # seguridad: nada del universo queda abierto aunque no esté atribuido a un libro
        for sym, qty in self.broker.positions().items():
            if sym in self.universe and qty > 0:
                self.incident(f"posición huérfana en {sym} ({qty}); cierre defensivo", symbol=sym)
                self.broker.cancel_all_for(sym)
                o = self.broker.sell_market(sym, qty, order_key("X", self.today, sym, "SELL", int(now_et().timestamp()) % 100000, self.version))
                self.broker.wait_fill(str(o.id), 45.0)
        self.log(type="check", strategy="ALL", key=key, action="eod_close")

    # ------------------------------------------------------------------ planificación y ejecución
    def schedule(self) -> list[tuple[datetime, str, callable]]:
        ss = self.cfg.session
        w0 = at(self.today, ss[f"{self.window}_start"]); w1 = at(self.today, ss[f"{self.window}_end"])
        ev: list[tuple[datetime, str, callable]] = []
        for s in self.cfg.strategies():
            if s.key == "S1":
                t = s.params["entry_time"]; ev.append((at(self.today, t), check_key(s.key, self.today, t), lambda s=s, k=check_key(s.key, self.today, t): self.check_s1(s, k)))
            elif s.key == "S3":
                t = s.params["entry_time"]; ev.append((at(self.today, t), check_key(s.key, self.today, t), lambda s=s, k=check_key(s.key, self.today, t): self.check_s3(s, k)))
            elif s.key == "S2":
                for t in s.params["check_times"]:
                    mark = parse_hms(t).replace(second=0)
                    ev.append((at(self.today, t), check_key(s.key, self.today, t), lambda s=s, k=check_key(s.key, self.today, t), m=mark: self.check_s2(s, k, m)))
        t = ss["eod_close"]; ev.append((at(self.today, t), check_key("ALL", self.today, t), lambda k=check_key("ALL", self.today, t): self.eod_close(k)))
        return sorted([e for e in ev if w0 <= e[0] <= w1], key=lambda e: e[0])

    def run(self) -> dict:
        self.log(type="session_start", window=self.window, version=self.version)
        ok, why = self.market_open_today()
        if not ok:
            self.log(type="session_end", window=self.window, skipped=True, reason=why); return {"skipped": why}
        try:
            self.reconcile()
            for when, key, fn in self.schedule():
                if journal.has_key(key, self.today):
                    continue
                if when > now_et(): sleep_until(when)
                try:
                    self.sync_stops()
                    fn()
                except RuntimeError as e:          # límite de órdenes: abortar la ventana
                    self.incident(f"abortada la ventana: {e}"); break
                except Exception as e:             # noqa: BLE001  fallo de una revisión: registrar y seguir
                    self.incident(f"error en {key}: {e}", trace=traceback.format_exc()[-1500:])
                finally:
                    self.state.save()
            self.sync_stops()
        finally:
            summary = {"window": self.window, "incidents": len(self.incidents), "books": {k: b.equity for k, b in self.state.books.items()}}
            try:
                summary["account_equity"] = self.broker.account_equity()
                if self.window == "afternoon":
                    for b in self.state.books.values(): self.log(type="eod_mark", strategy=b.strategy, equity=b.equity)
                    spy = self.data.minute_bars("SPY", self.today)
                    if not spy.empty: summary["spy_close"] = float(spy["close"].iloc[-1])
            except Exception as e:  # noqa: BLE001
                self.incident(f"resumen de sesión incompleto: {e}")
            self.state.last_session = {**summary, "ts": now_et().isoformat(timespec="seconds")}
            self.state.save()
            self.log(type="session_end", **summary)
        return summary
