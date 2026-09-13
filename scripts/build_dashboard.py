"""Regenera docs/data/dashboard.json. Con --demo genera un diario de ejemplo en un directorio temporal para previsualizar."""
from __future__ import annotations
import argparse, json, os, random, sys, tempfile
from datetime import date, timedelta, datetime, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor import journal, report
from motor.clock import ET
from motor.config import load as load_cfg
from motor.risk import State, Book


def make_demo(days: int = 45) -> tuple[State, Path]:
    """Diario sintético y claramente etiquetado como demo: solo sirve para ver el dashboard antes de la primera sesión."""
    rnd = random.Random(7)
    tmp = Path(tempfile.mkdtemp(prefix="motor-demo-"))
    journal.JOURNAL_DIR = tmp
    cfg = load_cfg(); st = State()
    eq = {s.key: 10000.0 for s in cfg.strategies()}
    spy = 640.0
    d = date.today() - timedelta(days=int(days * 1.45))
    n = 0
    while n < days:
        d += timedelta(days=1)
        if d.weekday() >= 5: continue
        n += 1
        spy *= 1 + rnd.gauss(0.0004, 0.009)
        for s in cfg.strategies():
            b = st.book(s.key, 10000.0)
            if rnd.random() < {"S1": 0.85, "S2": 0.55, "S3": 0.3}[s.key]:
                up = rnd.random() < 0.5
                sym = s.long_symbol if up else s.short_symbol
                px = {"TQQQ": 78.0, "SQQQ": 24.0, "SPY": spy, "SH": 36.0, "QQQ": 560.0, "PSQ": 33.0}[sym] * (1 + rnd.gauss(0, 0.02))
                stop_pct = {"S1": 0.012, "S2": 0.004, "S3": 0.006}[s.key] * (1 + rnd.random())
                qty = int(min(0.01 * eq[s.key] / (stop_pct * px), eq[s.key] / px))
                edge = {"S1": 0.0002, "S2": 0.0004, "S3": -0.0003}[s.key]
                ret = rnd.gauss(edge, stop_pct * 1.1)
                ret = max(ret, -stop_pct)
                exit_px = px * (1 + ret)
                tid = f"{s.key}-{d:%Y%m%d}-{sym}-BUY-{b.n_trades + 1}-v1.0"
                ts_in = datetime.combine(d, time(9, 35, 7) if s.key == "S1" else time(10, 0, 6) if s.key == "S3" else time(rnd.choice([10, 11, 13, 14]), rnd.choice([0, 30]), 6), tzinfo=ET)
                journal.append({"type": "entry", "strategy": s.key, "trade_id": tid, "symbol": sym, "qty": qty, "entry_price": round(px, 2),
                                "delay_bps": abs(rnd.gauss(3, 2)), "reason": "demo", "arrival_mid": round(px * 0.9998, 2)}, d)
                gross = (exit_px - px) * qty
                nets = {f"net_{bps}bps": gross - bps / 1e4 * (px + exit_px) * qty for bps in (5, 10)}
                booked = nets["net_10bps"]
                b.apply_pnl(booked, d, cfg.limits); eq[s.key] = b.equity
                journal.append({"type": "exit", "strategy": s.key, "trade_id": tid, "symbol": sym, "qty": qty, "entry_price": round(px, 2), "exit_price": round(exit_px, 2),
                                "pnl_gross": gross, **nets, "pnl_booked": booked, "reason": rnd.choice(["cierre de sesión 15:55", "stop ejecutado en el servidor", "precio vuelve dentro de la banda"]),
                                "source": "eod", "limits_fired": [], "book_equity": b.equity}, d)
            journal.append({"type": "eod_mark", "strategy": s.key, "equity": eq[s.key]}, d)
        if n % 9 == 0:
            journal.append({"type": "incident", "msg": "latencia de datos 2,4 s > límite; revisión omitida (demo)"}, d)
        journal.append({"type": "session_end", "window": "afternoon", "incidents": 0, "spy_close": round(spy, 2), "account_equity": 100000 + sum(eq.values()) - 30000}, d)
    st.last_session = {"window": "afternoon", "ts": datetime.combine(d, time(16, 4), tzinfo=ET).isoformat(), "account_equity": 100000 + sum(eq.values()) - 30000, "spy_close": round(spy, 2), "incidents": 0}
    return st, tmp


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--demo", action="store_true"); a = ap.parse_args()
    if a.demo:
        st, tmp = make_demo()
        out = report.write(state=st, demo=True)
    else:
        out = report.write()
    data = json.loads(out.read_text())
    print(f"{out} escrito: {len(data['trades'])} operaciones, {len(data['incidents'])} incidentes, demo={data['demo']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
