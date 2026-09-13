"""Construye docs/data/dashboard.json a partir del diario y del estado. Sin dependencias del broker."""
from __future__ import annotations
import json, math, statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from . import journal
from .clock import ET, now_et, at, parse_hms
from .config import ROOT, Config, load as load_cfg
from .risk import State, STATE_PATH

OUT = ROOT / "docs" / "data" / "dashboard.json"


def _metrics(pnls: list[float], equity_curve: list[float], start_equity: float) -> dict:
    n = len(pnls)
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    gp, gl = sum(wins), -sum(losses)
    # Sharpe sobre rendimientos diarios de la curva de equity
    rets = [equity_curve[i] / equity_curve[i - 1] - 1 for i in range(1, len(equity_curve)) if equity_curve[i - 1] > 0]
    sharpe = (statistics.fmean(rets) / statistics.pstdev(rets) * math.sqrt(252)) if len(rets) > 2 and statistics.pstdev(rets) > 0 else None
    peak, mdd = -1e18, 0.0
    for e in equity_curve:
        peak = max(peak, e); mdd = max(mdd, (peak - e) / peak if peak > 0 else 0.0)
    return {"n_trades": n, "win_rate": (len(wins) / n) if n else None, "profit_factor": (gp / gl) if gl > 0 else (None if not wins else float("inf")),
            "avg_pnl": (sum(pnls) / n) if n else None, "total_pnl": sum(pnls), "return_pct": (equity_curve[-1] / start_equity - 1) if equity_curve else 0.0,
            "sharpe": sharpe, "max_drawdown": mdd}


def _day(e: dict) -> str:
    return e.get("date") or e["ts"][:10]


def build(cfg: Config | None = None, state: State | None = None, demo: bool = False) -> dict:
    cfg = cfg or load_cfg(); state = state or State.load()
    start_eq = float(cfg.account["book_equity_start"])
    events = list(journal.iter_all())
    entries = {e["trade_id"]: e for e in events if e.get("type") == "entry"}
    trades, incidents, marks, checks, sessions = [], [], defaultdict(dict), [], []
    for e in events:
        t = e.get("type")
        if t == "exit":
            en = entries.get(e.get("trade_id"), {})
            trades.append({"date": _day(e), "strategy": e["strategy"], "symbol": e["symbol"], "qty": e["qty"],
                           "entry_price": e["entry_price"], "exit_price": e["exit_price"], "pnl_gross": e["pnl_gross"],
                           "pnl_net_5bps": e.get("net_5bps"), "pnl_net_10bps": e.get("net_10bps"), "pnl_booked": e["pnl_booked"],
                           "reason": e["reason"], "source": e["source"], "delay_bps": en.get("delay_bps"), "entry_ts": en.get("ts"), "exit_ts": e["ts"],
                           "entry_reason": en.get("reason")})
        elif t == "incident": incidents.append({"ts": e["ts"], "msg": e["msg"], "extra": {k: v for k, v in e.items() if k not in ("ts", "type", "msg", "window")}})
        elif t == "eod_mark": marks[e["strategy"]][_day(e)] = e["equity"]
        elif t == "check": checks.append({"ts": e["ts"], "strategy": e["strategy"], "action": e.get("action"), "reason": e.get("reason")})
        elif t == "session_end": sessions.append(e)
    spy = {}
    for s in sessions:
        if s.get("spy_close"): spy[_day(s)] = s["spy_close"]
    days = sorted({d for m in marks.values() for d in m} | set(spy))
    strategies = {}
    for s in cfg.strategies():
        b = state.books.get(s.key)
        curve = [start_eq] + [marks[s.key][d] for d in days if d in marks[s.key]]
        pnls = [t["pnl_booked"] for t in trades if t["strategy"] == s.key]
        delays = [t["delay_bps"] for t in trades if t["strategy"] == s.key and t["delay_bps"] is not None]
        strategies[s.key] = {"name": s.name, "symbols": list(s.symbols), "signal_symbol": s.signal_symbol,
                             "equity": b.equity if b else start_eq, "equity_start": start_eq,
                             "status": ("apagado" if b and b.disabled else "en pausa" if b and b.paused_until else "activo"),
                             "status_detail": (b.disabled_reason if b and b.disabled else f"hasta {b.paused_until}" if b and b.paused_until else ""),
                             "open_position": ({"symbol": b.open_symbol, "qty": b.open_qty, "entry_price": b.open_entry_price} if b and b.open_symbol else None),
                             "metrics": _metrics(pnls, curve, start_eq), "avg_delay_bps": statistics.fmean(delays) if delays else None,
                             "curve": [{"date": d, "equity": marks[s.key][d]} for d in days if d in marks[s.key]]}
    spy_curve = []
    if spy:
        d0 = days[0] if days else sorted(spy)[0]; base = spy.get(d0) or spy[sorted(spy)[0]]
        spy_curve = [{"date": d, "equity": start_eq * spy[d] / base} for d in sorted(spy)]
    now = now_et()
    return {"generated_at": now.isoformat(timespec="seconds"), "demo": demo, "version": state.version,
            "criteria": {"eval_months": 6, "min_sharpe_net_10bps": 0.5, "min_trades": 60, "max_avg_delay_bps": 10},
            "last_session": state.last_session, "orders_today": state.orders_today if state.orders_day == now.date().isoformat() else 0,
            "next_event": _next_event(cfg, now), "strategies": strategies, "trades": sorted(trades, key=lambda t: (t["date"], t["exit_ts"]), reverse=True),
            "incidents": sorted(incidents, key=lambda i: i["ts"], reverse=True)[:50], "recent_checks": sorted(checks, key=lambda c: c["ts"], reverse=True)[:40],
            "spy_curve": spy_curve, "limits": cfg.limits}


def _next_event(cfg: Config, now: datetime) -> dict:
    times = []
    for s in cfg.strategies():
        if "entry_time" in s.params: times.append((s.params["entry_time"], f"{s.key}: revisión de entrada"))
        for t in s.params.get("check_times", []): times.append((t, f"{s.key}: revisión de banda"))
    times.append((cfg.session["eod_close"], "cierre de todas las posiciones"))
    for d in range(0, 8):
        day = now.date() + timedelta(days=d)
        if day.weekday() >= 5: continue
        for t, label in sorted(times):
            when = at(day, t)
            if when > now: return {"when": when.isoformat(timespec="seconds"), "label": label}
    return {}


def write(**kw) -> Path:
    data = build(**kw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str))
    return OUT
