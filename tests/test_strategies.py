from datetime import time
import pytest
from motor.strategies import orb, noise_band, fade_open
from tests.conftest import make_bars, DAY


def test_orb_alcista(cfg):
    s1 = cfg.strategy("S1")
    bars = make_bars([100.0, 100.4, 100.6, 100.5, 101.0])  # cierra por encima de la apertura
    d = orb.decide(bars, s1, DAY)
    assert d.is_enter and d.symbol == "TQQQ"
    # R = (close - range_low)/close = (101 - 99.95)/101, ×3 por el apalancamiento
    assert d.stop_pct == pytest.approx(3 * (101.0 - 99.95) / 101.0)


def test_orb_bajista(cfg):
    s1 = cfg.strategy("S1")
    bars = make_bars([100.0, 99.7, 99.5, 99.6, 99.0])
    d = orb.decide(bars, s1, DAY)
    assert d.is_enter and d.symbol == "SQQQ"
    assert d.stop_pct == pytest.approx(3 * (100.05 - 99.0) / 99.0)


def test_orb_plana_y_barras_insuficientes(cfg):
    s1 = cfg.strategy("S1")
    assert orb.decide(make_bars([100.0] * 5), s1, DAY).action == "skip"
    assert orb.decide(make_bars([100.0, 101.0, 102.0]), s1, DAY).action == "skip"
    assert orb.decide(make_bars([100.0, 101.0]).iloc[0:0], s1, DAY).action == "skip"


def _history(n=14, move=0.005):
    # días anteriores: apertura 100, a las 10:00 el precio se ha movido ±move
    hist = []
    for i in range(n):
        sign = 1 if i % 2 == 0 else -1
        closes = [100.0] * 5 + [100.0 * (1 + sign * move)] * 26
        hist.append(make_bars(closes))
    return hist


def test_noise_band_sigma_y_entrada(cfg):
    s2 = cfg.strategy("S2")
    hist = _history()
    sigma = noise_band.sigma_by_time(hist, time(10, 0))
    assert sigma == pytest.approx(0.005)
    # hoy: apertura 100, cierre previo 100, precio a las 10:00 en 101 (> banda 100.5 y > VWAP)
    today = make_bars([100.0] * 10 + [100.2, 100.6, 101.0] + [101.0] * 18)
    d = noise_band.decide(today, prev_close=100.0, sigma=sigma, mark=time(10, 0), in_position=None, cfg=s2)
    assert d.is_enter and d.symbol == "SPY"
    assert d.stop_pct == pytest.approx((101.0 - 100.5) / 101.0)


def test_noise_band_salida_y_dentro(cfg):
    s2 = cfg.strategy("S2")
    sigma = 0.005
    inside = make_bars([100.0] * 31)
    assert noise_band.decide(inside, 100.0, sigma, time(10, 0), None, s2).action == "skip"
    # con posición larga y precio de vuelta dentro de la banda → salir
    assert noise_band.decide(inside, 100.0, sigma, time(10, 0), "SPY", s2).action == "exit"
    # con posición larga y precio fuera → mantener con stop en la banda
    above = make_bars([100.0] * 20 + [101.0] * 11)
    h = noise_band.decide(above, 100.0, sigma, time(10, 0), "SPY", s2)
    assert h.action == "hold" and h.stop_pct > 0
    # ruptura bajista → SH
    below = make_bars([100.0] * 20 + [99.0] * 11)
    assert noise_band.decide(below, 100.0, sigma, time(10, 0), None, s2).symbol == "SH"


def test_fade_open(cfg):
    s3 = cfg.strategy("S3")
    hist = _history(move=0.004)  # σ ≈ 0.004 (movimientos ±0.4 %)
    # caída de 1 % en la apertura → rebote con QQQ
    down = make_bars([100.0] * 5 + [99.0] * 26)
    d = fade_open.decide(down, hist, s3)
    assert d.is_enter and d.symbol == "QQQ" and d.stop_pct == pytest.approx(d.meta["sigma"])
    up = make_bars([100.0] * 5 + [101.0] * 26)
    assert fade_open.decide(up, hist, s3).symbol == "PSQ"
    calm = make_bars([100.0] * 5 + [100.1] * 26)
    assert fade_open.decide(calm, hist, s3).action == "skip"
    assert fade_open.decide(down, hist[:3], s3).action == "skip"
