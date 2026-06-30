"""选股筛选器 pytest · 股票第一批 功能1 · 1a MVP(纯逻辑 · 无 DB · 本地秒级可跑)。

覆盖:
- schema 守卫(is_empty / needs_kline);
- 预筛 / 技术过滤纯函数(_spot_pass / _tech_pass);
- select_klines_batch 分组 + reverse(fake raw client · 不打真 DB);
- run_screener:纯 spot 分支 / RSI 技术分支 / 候选上限 capped / 分页 / 红线免责。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.schemas.market import Kline
from app.schemas.screener import ScreenerFilters
from app.services import screener
from app.services.ai import strategy_signals
from app.services.clickhouse_client import ClickHouseClient


def _klines(closes: list[float]) -> list[Kline]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Kline(
            ts=base + timedelta(days=i),
            open=c, high=c, low=c, close=c, volume=1000.0, amount=None,
        )
        for i, c in enumerate(closes)
    ]


def _spot(symbol: str, price: float, chg: float, amount: float) -> Any:
    return SimpleNamespace(
        symbol=symbol, name=f"N{symbol}", last_price=price,
        change_pct=chg, amount=amount,
    )


# ── schema 守卫 ──────────────────────────────────────────────────────


def test_filters_is_empty():
    assert ScreenerFilters().is_empty() is True
    assert ScreenerFilters(price_min=10).is_empty() is False


def test_filters_needs_kline():
    assert ScreenerFilters(price_min=10).needs_kline() is False
    assert ScreenerFilters(rsi_min=30).needs_kline() is True
    assert ScreenerFilters(ma_bull_aligned=True).needs_kline() is True
    assert ScreenerFilters(macd_golden_cross=True).needs_kline() is True
    assert ScreenerFilters(kdj_golden_cross=True).needs_kline() is True
    assert ScreenerFilters(boll_bandwidth_max=10).needs_kline() is True
    assert ScreenerFilters(volume_ratio_min=2).needs_kline() is True


# ── 预筛 / 技术过滤纯函数 ────────────────────────────────────────────


def test_spot_pass_price_change():
    row = _spot("A", 50.0, 3.0, 1000)
    assert screener._spot_pass(row, ScreenerFilters(price_max=60)) is True
    assert screener._spot_pass(row, ScreenerFilters(price_max=40)) is False
    assert screener._spot_pass(row, ScreenerFilters(change_pct_min=5)) is False
    assert screener._spot_pass(row, ScreenerFilters(change_pct_min=2, change_pct_max=4)) is True


def test_tech_pass_rsi_and_ma():
    ma_bull = {5: 12.0, 20: 11.0, 60: 10.0}  # 多头排列
    ma_flat = {5: 10.0, 20: 11.0, 60: 12.0}  # 空头(非多头)

    def call(f: ScreenerFilters, rsi: float | None, ma: dict[int, float]) -> bool:
        return screener._tech_pass(f, rsi=rsi, ma=ma, macd_g=False, kdj_g=False, bw=None, vr=1.0)

    assert call(ScreenerFilters(rsi_min=60), 70.0, ma_bull) is True
    assert call(ScreenerFilters(rsi_min=60), 50.0, ma_bull) is False
    assert call(ScreenerFilters(rsi_min=60), None, ma_bull) is False
    assert call(ScreenerFilters(ma_bull_aligned=True), 70.0, ma_bull) is True
    assert call(ScreenerFilters(ma_bull_aligned=True), 70.0, ma_flat) is False


def test_tech_pass_1b_conditions():
    ma = {5: 12.0, 20: 11.0, 60: 10.0}
    f_macd = ScreenerFilters(macd_golden_cross=True)
    assert screener._tech_pass(f_macd, rsi=50.0, ma=ma, macd_g=True, kdj_g=False, bw=None, vr=1.0) is True
    assert screener._tech_pass(f_macd, rsi=50.0, ma=ma, macd_g=False, kdj_g=False, bw=None, vr=1.0) is False
    f_kdj = ScreenerFilters(kdj_golden_cross=True)
    assert screener._tech_pass(f_kdj, rsi=50.0, ma=ma, macd_g=False, kdj_g=True, bw=None, vr=1.0) is True
    f_bw = ScreenerFilters(boll_bandwidth_max=10)  # 带宽 ≤ 10% 收窄
    assert screener._tech_pass(f_bw, rsi=50.0, ma=ma, macd_g=False, kdj_g=False, bw=8.0, vr=1.0) is True
    assert screener._tech_pass(f_bw, rsi=50.0, ma=ma, macd_g=False, kdj_g=False, bw=15.0, vr=1.0) is False
    f_vr = ScreenerFilters(volume_ratio_min=2)
    assert screener._tech_pass(f_vr, rsi=50.0, ma=ma, macd_g=False, kdj_g=False, bw=None, vr=2.5) is True
    assert screener._tech_pass(f_vr, rsi=50.0, ma=ma, macd_g=False, kdj_g=False, bw=None, vr=1.5) is False


def test_latest_golden_cross_helpers():
    # 数据不足 → False
    assert strategy_signals.latest_macd_golden_cross([]) is False
    assert strategy_signals.latest_kdj_golden_cross([]) is False
    # 长平盘后末根跳涨 → DIF/K 上穿 → 金叉 True
    spike = _klines([100.0] * 40 + [120.0])
    assert strategy_signals.latest_macd_golden_cross(spike) is True
    assert strategy_signals.latest_kdj_golden_cross(spike) is True
    # 全平盘 → 无穿越 → False
    flat = _klines([100.0] * 41)
    assert strategy_signals.latest_macd_golden_cross(flat) is False


# ── select_klines_batch 分组 + reverse ──────────────────────────────


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.result_rows = rows


class _FakeRawClient:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self.queried = False
        self.last_params: dict[str, Any] | None = None

    async def query(self, _sql: str, parameters: dict[str, Any] | None = None) -> _FakeResult:
        self.queried = True
        self.last_params = parameters  # 用掉 parameters(避免 unused · 关键字须匹配真调用方)
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_select_klines_batch_groups_and_reverses():
    t1 = datetime(2026, 6, 30, 8, 0, tzinfo=UTC)
    t0 = datetime(2026, 6, 29, 8, 0, tzinfo=UTC)
    # DB 返回 ts DESC(新→旧)· 期望分组 + 每组 reverse 成 ASC(旧→新)
    rows = [
        ("AAA", t1, 11.0, 12.0, 10.0, 11.5, 100.0, 0.0),
        ("AAA", t0, 10.0, 11.0, 9.0, 10.5, 90.0, 0.0),
        ("BBB", t1, 20.0, 21.0, 19.0, 20.5, 200.0, 0.0),
    ]
    ch = ClickHouseClient(cast("Any", _FakeRawClient(rows)))
    out = await ch.select_klines_batch(
        symbols=["AAA", "BBB"], market="cn", period="1d", limit=120,
    )
    assert set(out) == {"AAA", "BBB"}
    assert [k.ts for k in out["AAA"]] == [t0, t1]  # reverse 成 ASC
    assert out["AAA"][-1].close == 11.5  # 末根 = 最新
    assert len(out["BBB"]) == 1


@pytest.mark.asyncio
async def test_select_klines_batch_empty_skips_db():
    raw = _FakeRawClient([])
    ch = ClickHouseClient(cast("Any", raw))
    out = await ch.select_klines_batch(symbols=[], market="cn", period="1d")
    assert out == {}
    assert raw.queried is False  # 空 symbols 不打 DB


# ── run_screener ────────────────────────────────────────────────────


class _FakeCH:
    def __init__(self, kmap: dict[str, list[Kline]]) -> None:
        self._kmap = kmap

    async def select_klines_batch(self, **_kw: Any) -> dict[str, list[Kline]]:
        return self._kmap


@pytest.mark.asyncio
async def test_run_screener_spot_only(monkeypatch: pytest.MonkeyPatch):
    pool = [_spot("A", 10.0, 5.0, 1000), _spot("B", 50.0, -2.0, 900), _spot("C", 10.0, 1.0, 800)]

    async def _fake_pool(_raw: Any, _market: str) -> list[Any]:
        return pool
    monkeypatch.setattr(screener, "_fetch_spot_pool", _fake_pool)

    f = ScreenerFilters(price_max=20)  # A,C ≤20 · B 50 排除 · 无技术 → 不算 K线
    resp = await screener.run_screener(
        cast("Any", _FakeCH({})), cast("Any", None), market="cn", filters=f,
    )
    assert {h.symbol for h in resp.hits} == {"A", "C"}
    assert resp.candidate_capped is False
    assert resp.scanned == 2
    assert "不构成投资建议" in resp.disclaimer


@pytest.mark.asyncio
async def test_run_screener_rsi_filters(monkeypatch: pytest.MonkeyPatch):
    pool = [_spot("UP", 10.0, 5.0, 1000), _spot("DN", 10.0, 5.0, 900)]

    async def _fake_pool(_raw: Any, _market: str) -> list[Any]:
        return pool
    monkeypatch.setattr(screener, "_fetch_spot_pool", _fake_pool)

    kmap = {
        "UP": _klines([100.0 + i for i in range(70)]),   # 全涨 → RSI 高
        "DN": _klines([200.0 - i for i in range(70)]),   # 全跌 → RSI 低
    }
    f = ScreenerFilters(rsi_min=60)
    resp = await screener.run_screener(
        cast("Any", _FakeCH(kmap)), cast("Any", None), market="cn", filters=f,
    )
    assert {h.symbol for h in resp.hits} == {"UP"}
    assert resp.hits[0].rsi_14 is not None
    assert resp.hits[0].rsi_14 >= 60


@pytest.mark.asyncio
async def test_run_screener_capped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(screener, "_MAX_TECH_SCAN", 1)  # 候选上限缩到 1 测 capped
    pool = [_spot("A", 10.0, 5.0, 1000), _spot("B", 10.0, 5.0, 900)]

    async def _fake_pool(_raw: Any, _market: str) -> list[Any]:
        return pool
    monkeypatch.setattr(screener, "_fetch_spot_pool", _fake_pool)

    kmap = {"A": _klines([100.0 + i for i in range(70)])}  # 只 A(B 被 cap 掉)
    f = ScreenerFilters(rsi_min=0)
    resp = await screener.run_screener(
        cast("Any", _FakeCH(kmap)), cast("Any", None), market="cn", filters=f,
    )
    assert resp.candidate_capped is True  # pool 2 > _MAX_TECH_SCAN 1
    assert resp.scanned == 1
