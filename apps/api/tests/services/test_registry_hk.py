"""港股告警指标注册表扩展 pytest · 任务2 功能3(registry 扩 hk · 对称扩展)。

验证:
- 第一版 8 指标子集(price/涨跌幅/量/MA/MACD/RSI/布林)markets 含 hk;
- hk_breadth_up_ratio 已注册 + 元信息正确(市场级 · 无 symbol · 无 timeframe);
- hk 宽度 fetcher 逻辑(up/(up+down)·无数据 / 全停牌返 None · 不除零);
- ★回归保护:缠论 / 板块 / 指数第一版【不】扩 hk(恒指无采集 · 缠论不在 8 指标)。
纯逻辑(无 DB) · 本地秒级可跑。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.hk_market import HkBreadth
from app.services import clickhouse_hk_market
from app.services.alerts import registry
from app.services.alerts.registry import get_indicator

# 第一版港股告警 8 指标子集(总纲:price/涨跌幅/量/MA/MACD/RSI/布林/宽度)· MA 含 5/20/60
_HK_PER_SYMBOL_KEYS = (
    "price", "price_change_pct", "volume",
    "ma_5", "ma_20", "ma_60", "macd_hist", "rsi_14", "boll_pctb",
)
# 明确【不】扩 hk(不在第一版 8 指标:缠论灵敏度打折 · 板块 / 指数港股无对应采集)
_NOT_HK_KEYS = ("chan_buy", "chan_sell", "sector_change_pct", "index_change_pct")


@pytest.mark.parametrize("key", _HK_PER_SYMBOL_KEYS)
def test_hk_per_symbol_indicators_include_hk(key: str):
    ind = get_indicator(key)
    assert ind is not None, f"指标 {key} 应存在"
    assert "hk" in ind.markets, f"{key} 应支持港股(实际 markets={ind.markets})"


def test_hk_breadth_indicator_registered():
    ind = get_indicator("hk_breadth_up_ratio")
    assert ind is not None
    assert ind.markets == ("hk",)
    assert ind.category == "market_structure"
    assert ind.requires_symbol is False
    assert ind.needs_timeframe is False
    assert ind.unit == "%"


@pytest.mark.parametrize("key", _NOT_HK_KEYS)
def test_chan_sector_index_not_extended_to_hk(key: str):
    ind = get_indicator(key)
    assert ind is not None
    assert "hk" not in ind.markets, f"{key} 第一版不应扩 hk(实际 markets={ind.markets})"


def _breadth(up: int, down: int) -> HkBreadth:
    return HkBreadth(
        ts=datetime(2026, 6, 30, 8, 0, tzinfo=UTC),
        up_count=up, down_count=down, flat_count=0, total_amount=1_000_000.0,
    )


@pytest.mark.asyncio
async def test_hk_breadth_fetcher_up_ratio(monkeypatch: pytest.MonkeyPatch):
    async def _fake(_raw: object) -> HkBreadth:
        return _breadth(60, 40)
    monkeypatch.setattr(clickhouse_hk_market, "select_latest_breadth", _fake)
    ctx = registry.ScanContext(ch=None, raw=None)  # type: ignore[arg-type]
    val = await registry._f_hk_breadth_up_ratio(ctx, "hk", None, None)
    assert val == 60.0  # 60 / (60 + 40) * 100 · 港股无涨跌停 → 分母 = up + down


@pytest.mark.asyncio
async def test_hk_breadth_fetcher_none_when_no_data(monkeypatch: pytest.MonkeyPatch):
    async def _fake(_raw: object) -> None:
        return None
    monkeypatch.setattr(clickhouse_hk_market, "select_latest_breadth", _fake)
    ctx = registry.ScanContext(ch=None, raw=None)  # type: ignore[arg-type]
    assert await registry._f_hk_breadth_up_ratio(ctx, "hk", None, None) is None


@pytest.mark.asyncio
async def test_hk_breadth_fetcher_none_when_total_zero(monkeypatch: pytest.MonkeyPatch):
    async def _fake(_raw: object) -> HkBreadth:
        return _breadth(0, 0)  # 全停牌 → 分母 0 → None(不除零)
    monkeypatch.setattr(clickhouse_hk_market, "select_latest_breadth", _fake)
    ctx = registry.ScanContext(ch=None, raw=None)  # type: ignore[arg-type]
    assert await registry._f_hk_breadth_up_ratio(ctx, "hk", None, None) is None
