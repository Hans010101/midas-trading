"""智能交易 PR-3 · 策略引擎纯函数测(打分共振 + ATR 止损止盈 + 阈值边界 + 批量)。

★纯函数:输入快照 dict + 价 → 输出决策 · 本地无需 PG/Redis 可跑(吸取教训:本地能跑必真跑)。
"""

from __future__ import annotations

from app.services.virtual_trading.intelligent import strategy as st


def _sig(**dirs: object) -> dict[str, object]:
    """intelligent 快照该币(方向分 + atr)· 缺省方向 0 · atr 默认 10。"""
    base: dict[str, object] = {
        "symbol": "BTCUSDT", "ma_dir": 0, "macd_dir": 0, "rsi_dir": 0,
        "kdj_dir": 0, "extreme_dir": 0, "atr": 10.0,
    }
    base.update(dirs)
    return base


def _boll(bias: str, close: float = 100.0) -> dict[str, object]:
    return {"symbol": "BTCUSDT", "bias": bias, "close": close}


# ── 打分 + 决策 ──────────────────────────────────────────────────────
def test_all_bullish_opens_long() -> None:
    # 全偏多:布林2.0+MACD1.5+MA1.5+RSI1.0+KDJ1.0+extreme1.0 = 8.0 > 3.0 → 开多
    d = st.decide("BTCUSDT", _boll("偏多"), _sig(
        ma_dir=1, macd_dir=1, rsi_dir=1, kdj_dir=1, extreme_dir=1), 100.0)
    assert d.action == "open_long"
    assert d.score == 8.0
    # ATR=10 · 止损=100−2×10=80 · 止盈=100+4×10=140(2:1)
    assert d.stop_loss == 80.0
    assert d.take_profit == 140.0


def test_all_bearish_opens_short() -> None:
    d = st.decide("BTCUSDT", _boll("偏空"), _sig(
        ma_dir=-1, macd_dir=-1, rsi_dir=-1, kdj_dir=-1, extreme_dir=-1), 100.0)
    assert d.action == "open_short"
    assert d.score == -8.0
    assert d.stop_loss == 120.0   # 开空止损 = 100+2×10
    assert d.take_profit == 60.0  # 开空止盈 = 100−4×10


def test_boll_plus_ma_just_over_threshold() -> None:
    # 布林2.0 + MA1.5 = 3.5 > 3.0 → 开多(其余中性)
    d = st.decide("BTCUSDT", _boll("偏多"), _sig(ma_dir=1), 100.0)
    assert d.action == "open_long"
    assert d.score == 3.5


def test_exactly_threshold_holds() -> None:
    # ★布林2.0 + RSI1.0 = 3.0 = 阈值 → 不开(需严格 > 3.0)
    d = st.decide("BTCUSDT", _boll("偏多"), _sig(rsi_dir=1), 100.0)
    assert d.action == "hold"
    assert d.score == 3.0
    assert d.stop_loss is None
    assert d.take_profit is None


def test_mixed_conflict_holds() -> None:
    # 布林偏多2.0 − MACD偏空1.5 = 0.5 → 不开
    d = st.decide("BTCUSDT", _boll("偏多"), _sig(macd_dir=-1), 100.0)
    assert d.action == "hold"
    assert d.score == 0.5


def test_atr_zero_no_stops() -> None:
    d = st.decide("BTCUSDT", _boll("偏多"), _sig(
        ma_dir=1, macd_dir=1, atr=0), 100.0)
    assert d.action == "open_long"  # score=5.0
    assert d.stop_loss is None      # ★ATR=0 → 无止损价
    assert d.take_profit is None


def test_boll_missing_drops_weight() -> None:
    # 布林缺(boll_item=None)→ boll 方向分 0(少 2.0 权重)· MA+MACD+RSI+KDJ=5.0 仍 > 3.0
    d = st.decide("BTCUSDT", None, _sig(
        ma_dir=1, macd_dir=1, rsi_dir=1, kdj_dir=1), 100.0)
    assert d.contributions["boll"] == 0
    assert d.score == 5.0
    assert d.action == "open_long"


def test_contributions_detail() -> None:
    d = st.decide("BTCUSDT", _boll("偏多"), _sig(ma_dir=1, macd_dir=-1), 100.0)
    assert d.contributions == {
        "boll": 1, "macd": -1, "ma": 1, "rsi": 0, "kdj": 0, "extreme": 0,
    }


# ── 批量 build_decisions + open_decisions ────────────────────────────
def test_build_decisions_indexes_and_skips() -> None:
    boll = [_boll("偏多", 100.0), {"symbol": "ETHUSDT", "bias": "偏空", "close": 50.0}]
    signals = [
        _sig(symbol="BTCUSDT", ma_dir=1, macd_dir=1, rsi_dir=1, kdj_dir=1, extreme_dir=1),
        _sig(symbol="ETHUSDT", ma_dir=-1, macd_dir=-1, rsi_dir=-1, kdj_dir=-1, extreme_dir=-1),
        _sig(symbol="NOBOLLUSDT", ma_dir=1),  # ★无 boll → 跳过
    ]
    decisions = st.build_decisions(boll, signals)
    assert len(decisions) == 2  # NOBOLL 跳过
    by_sym = {d.symbol: d for d in decisions}
    assert by_sym["BTCUSDT"].action == "open_long"
    assert by_sym["ETHUSDT"].action == "open_short"
    assert by_sym["ETHUSDT"].entry_price == 50.0  # ★price 取自 boll.close


def test_open_decisions_filters_hold() -> None:
    boll = [_boll("偏多"), {"symbol": "ETHUSDT", "bias": "中性", "close": 50.0}]
    signals = [
        _sig(symbol="BTCUSDT", ma_dir=1, macd_dir=1, rsi_dir=1, kdj_dir=1, extreme_dir=1),
        _sig(symbol="ETHUSDT"),  # 全中性 → hold
    ]
    opens = st.open_decisions(st.build_decisions(boll, signals))
    assert len(opens) == 1
    assert opens[0].symbol == "BTCUSDT"


def test_atr_stop_tp_independent_of_leverage() -> None:
    # ★★智能特殊点钉死:ATR 止损止盈是纯价格(entry∓N×ATR)· decide() 不接受 leverage 参数 ·
    # 杠杆可调【不影响】止损止盈价(与托管 tp_pct÷杠杆 不同)。entry=100 ATR=10 → 止损 80/止盈 140 恒定。
    d = st.decide("BTCUSDT", _boll("偏多"), _sig(
        ma_dir=1, macd_dir=1, rsi_dir=1, kdj_dir=1, extreme_dir=1, atr=10.0), 100.0)
    assert d.stop_loss == 80.0   # entry−2×ATR · 不除杠杆
    assert d.take_profit == 140.0  # entry+4×ATR · 不除杠杆
    # decide 签名无 leverage(纯价格)· 这是与托管 tp_pct 的关键区别
    import inspect  # noqa: PLC0415
    assert "leverage" not in inspect.signature(st.decide).parameters
