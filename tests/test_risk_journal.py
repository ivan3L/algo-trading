from datetime import date
import pytest
from motor import journal, risk
from motor.clock import order_key, check_key, first_of_next_month


def test_size_position():
    # 1 % de 10.000 = 100 $ de riesgo; stop 2 % sobre 50 $ = 1 $ por título → 100 títulos
    assert risk.size_position(10_000, 50.0, 0.02, 0.01, 1.0) == 100
    # tope de notional: 100 % de 10.000 / 50 = 200 títulos; con stop 0,2 % el riesgo pediría 1000
    assert risk.size_position(10_000, 50.0, 0.002, 0.01, 1.0) == 200
    assert risk.size_position(10_000, 50.0, 0.0, 0.01, 1.0) == 0
    assert risk.size_position(10_000, 20_000.0, 0.02, 0.01, 1.0) == 0


def test_book_limites():
    limits = {"monthly_loss_pause": 0.12, "drawdown_disable": 0.50}
    b = risk.Book("S1", 10_000, 10_000)
    d = date(2026, 10, 5)
    assert b.can_trade(d, 1) == (True, "ok")
    b.trades_today = 1
    assert b.can_trade(d, 1)[0] is False
    b.trades_today = 0
    fired = b.apply_pnl(-1300, d, limits)              # −13 % en el mes → pausa
    assert b.paused_until == "2026-11-01" and fired
    assert b.can_trade(d, 1)[0] is False
    assert b.can_trade(date(2026, 11, 2), 1)[0] is True  # la pausa expira
    b.apply_pnl(-4000, date(2026, 11, 3), limits)      # equity 4.700 → drawdown 53 % → apagado
    assert b.disabled and b.can_trade(date(2026, 12, 1), 1)[0] is False


def test_state_roundtrip(tmp_path):
    st = risk.State()
    b = st.book("S2", 10_000)
    b.open_symbol, b.open_qty = "SPY", 12
    st.count_order(date(2026, 9, 14), 20)
    p = tmp_path / "state.json"
    st.save(p)
    st2 = risk.State.load(p)
    assert st2.books["S2"].open_symbol == "SPY" and st2.books["S2"].open_qty == 12 and st2.orders_today == 1


def test_state_limite_ordenes():
    st = risk.State()
    for _ in range(3): st.count_order(date(2026, 9, 14), 3)
    with pytest.raises(RuntimeError):
        st.count_order(date(2026, 9, 14), 3)


def test_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path)
    d = date(2026, 9, 14)
    journal.append({"type": "check", "key": "S1|2026-09-14|09:35:05", "strategy": "S1"}, d)
    journal.append({"type": "incident", "msg": "prueba"}, d)
    assert journal.has_key("S1|2026-09-14|09:35:05", d) and not journal.has_key("otra", d)
    assert len(journal.read_day(d)) == 2 and len(list(journal.iter_all())) == 2


def test_claves():
    assert check_key("S1", date(2026, 9, 14), "09:35:05") == "S1|2026-09-14|09:35:05"
    k = order_key("S1", date(2026, 9, 14), "TQQQ", "BUY", 1, "v1.0")
    assert k == "S1-20260914-TQQQ-BUY-1-v1.0" and len(k) <= 48
    assert first_of_next_month(date(2026, 12, 31)) == date(2027, 1, 1)


def test_config_carga(cfg):
    keys = [s.key for s in cfg.strategies()]
    assert keys == ["S1", "S2", "S3"]
    assert cfg.strategy("S1").symbols == ("TQQQ", "SQQQ")
    assert cfg.limits["risk_per_trade"] == 0.01
    # los símbolos de ejecución no se repiten entre estrategias (atribución inequívoca)
    all_syms = [sym for s in cfg.strategies() for sym in s.symbols]
    assert len(all_syms) == len(set(all_syms))
