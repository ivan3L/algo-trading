"""Carga de configuración desde config/motor.toml. Sin dependencias externas."""
from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config" / "motor.toml"


@dataclass(frozen=True)
class StrategyConfig:
    key: str
    name: str
    signal_symbol: str
    long_symbol: str
    short_symbol: str
    leverage: float
    max_trades_per_day: int
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def symbols(self) -> tuple[str, str]:
        return (self.long_symbol, self.short_symbol)


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]

    @property
    def account(self) -> dict[str, Any]: return self.raw["account"]
    @property
    def limits(self) -> dict[str, Any]: return self.raw["limits"]
    @property
    def session(self) -> dict[str, Any]: return self.raw["session"]

    def strategies(self) -> list[StrategyConfig]:
        out = []
        for key, s in self.raw["strategies"].items():
            fixed = {"name", "signal_symbol", "long_symbol", "short_symbol", "leverage", "max_trades_per_day"}
            out.append(StrategyConfig(key=key, name=s["name"], signal_symbol=s["signal_symbol"], long_symbol=s["long_symbol"],
                                      short_symbol=s["short_symbol"], leverage=float(s["leverage"]),
                                      max_trades_per_day=int(s["max_trades_per_day"]),
                                      params={k: v for k, v in s.items() if k not in fixed}))
        return out

    def strategy(self, key: str) -> StrategyConfig:
        return next(s for s in self.strategies() if s.key == key)


def load(path: Path | str = DEFAULT_PATH) -> Config:
    with open(path, "rb") as f:
        return Config(raw=tomllib.load(f))
