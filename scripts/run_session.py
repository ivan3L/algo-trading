"""Ejecuta una ventana de sesión en paper. Uso: python scripts/run_session.py --window morning|afternoon [--cron-utc-hours 13 14] [--force]"""
from __future__ import annotations
import argparse, os, subprocess, sys
from datetime import timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor import config as cfgmod, report
from motor.clock import now_et, at, sleep_until, UTC
from motor.data import MarketData
from motor.execution import Broker
from motor.risk import State
from motor.session import Session
from datetime import datetime


def right_cron(hours: list[int]) -> bool:
    """Los cron son UTC y Nueva York cambia de hora: cada flujo se programa en dos horas UTC y solo actúa la correcta."""
    if not hours: return True
    is_dst = now_et().dst() != timedelta(0)
    expected = hours[0] if is_dst else hours[1]
    return datetime.now(tz=UTC).hour == expected


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", required=True, choices=["morning", "afternoon"])
    ap.add_argument("--cron-utc-hours", nargs=2, type=int, default=None, metavar=("EDT", "EST"))
    ap.add_argument("--force", action="store_true", help="ignora la comprobación de cron")
    a = ap.parse_args()
    if not a.force and not right_cron(a.cron_utc_hours or []):
        print("Este disparo de cron no corresponde a la hora de Nueva York objetivo; salgo sin hacer nada."); return 0
    key, secret = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        print("Faltan ALPACA_API_KEY / ALPACA_SECRET_KEY en el entorno.", file=sys.stderr); return 2
    cfg = cfgmod.load()
    start = at(now_et().date(), cfg.session[f"{a.window}_start"])
    if now_et() < start:
        print(f"Esperando al inicio de la ventana {a.window} a las {start.time()} ET…"); sleep_until(start)
    if os.environ.get("GITHUB_ACTIONS") == "true":   # recoge el estado que dejó la ventana anterior
        subprocess.run(["git", "pull", "--rebase", "--quiet"], check=False)
    broker = Broker(key, secret, paper=bool(cfg.account.get("paper", True)))
    data = MarketData(key, secret)
    state = State.load()
    summary = Session(a.window, cfg, broker, data, state).run()
    print("Resumen:", summary)
    report.write(cfg=cfg, state=State.load())
    return 0


if __name__ == "__main__":
    sys.exit(main())
