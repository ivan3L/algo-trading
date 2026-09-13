"""Libros virtuales por estrategia y límites duros. El estado vive en data/state.json."""
from __future__ import annotations
import json, math
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path
from .clock import first_of_next_month
from .config import ROOT

STATE_PATH = ROOT / "data" / "state.json"


@dataclass
class Book:
    strategy: str
    equity_start: float
    equity: float
    month: str = ""                 # "AAAA-MM" del mes en curso
    month_start_equity: float = 0.0
    paused_until: str | None = None # fecha ISO; None si no está en pausa
    disabled: bool = False
    disabled_reason: str = ""
    today: str = ""
    trades_today: int = 0
    open_symbol: str | None = None  # posición abierta atribuida a este libro
    open_qty: int = 0
    open_entry_price: float = 0.0
    open_stop_order_id: str | None = None
    realized_pnl_total: float = 0.0
    n_trades: int = 0

    def roll_day(self, d: date) -> None:
        if self.today != d.isoformat():
            self.today, self.trades_today = d.isoformat(), 0
        m = d.strftime("%Y-%m")
        if self.month != m:
            self.month, self.month_start_equity = m, self.equity
        if self.paused_until and date.fromisoformat(self.paused_until) <= d:
            self.paused_until = None

    def can_trade(self, d: date, max_trades_per_day: int) -> tuple[bool, str]:
        self.roll_day(d)
        if self.disabled: return False, f"libro apagado: {self.disabled_reason}"
        if self.paused_until: return False, f"libro en pausa hasta {self.paused_until}"
        if self.open_symbol: return False, f"ya hay posición abierta en {self.open_symbol}"
        if self.trades_today >= max_trades_per_day: return False, "máximo de operaciones del día alcanzado"
        return True, "ok"

    def apply_pnl(self, pnl: float, d: date, limits: dict) -> list[str]:
        """Aplica un P&L realizado y devuelve los límites que se hayan disparado."""
        self.roll_day(d)
        self.equity += pnl
        self.realized_pnl_total += pnl
        self.n_trades += 1
        fired = []
        if self.month_start_equity > 0 and (self.equity / self.month_start_equity - 1.0) <= -float(limits["monthly_loss_pause"]):
            self.paused_until = first_of_next_month(d).isoformat()
            fired.append(f"pérdida mensual > {limits['monthly_loss_pause']:.0%}: pausa hasta {self.paused_until}")
        if (self.equity / self.equity_start - 1.0) <= -float(limits["drawdown_disable"]):
            self.disabled, self.disabled_reason = True, f"drawdown ≥ {limits['drawdown_disable']:.0%} desde el inicio"
            fired.append(self.disabled_reason)
        return fired


def size_position(equity: float, price: float, stop_pct: float, risk_per_trade: float, max_notional_frac: float) -> int:
    """Títulos enteros: riesgo fijo por operación con tope de notional. 0 si no cabe ni un título."""
    if price <= 0 or stop_pct <= 0 or equity <= 0: return 0
    by_risk = math.floor(risk_per_trade * equity / (stop_pct * price))
    by_notional = math.floor(max_notional_frac * equity / price)
    return max(0, min(by_risk, by_notional))


@dataclass
class State:
    books: dict[str, Book] = field(default_factory=dict)
    orders_today: int = 0
    orders_day: str = ""
    version: str = "v1.0"
    last_session: dict = field(default_factory=dict)

    def book(self, strategy: str, equity_start: float) -> Book:
        if strategy not in self.books:
            self.books[strategy] = Book(strategy=strategy, equity_start=equity_start, equity=equity_start)
        return self.books[strategy]

    def count_order(self, d: date, max_orders: int) -> None:
        if self.orders_day != d.isoformat(): self.orders_day, self.orders_today = d.isoformat(), 0
        self.orders_today += 1
        if self.orders_today > max_orders:
            raise RuntimeError(f"límite de {max_orders} órdenes por sesión superado")

    def save(self, path: Path = STATE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self); data["books"] = {k: asdict(b) for k, b in self.books.items()}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "State":
        if not path.exists(): return cls()
        data = json.loads(path.read_text())
        books = {k: Book(**b) for k, b in data.pop("books", {}).items()}
        return cls(books=books, **data)
