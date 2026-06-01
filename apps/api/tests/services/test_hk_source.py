"""港股数据源 AKShareHkSource pytest · ADR 0034a P1-2(mock akshare · 不打真实上游)。

覆盖:
- fetch_kline 日线:mock stock_hk_hist → 字段映射正确(中文列 → Kline)+ ts 升序 + qfq。
- 周线(1w)同走 daily-like 映射。
- 不支持周期(1m/5m…)→ DataFormatError(阶段一只日/周)。
- 空 df → SymbolNotFoundError;字段不全 → DataFormatError。
- 代码 normalize(700 → 00700)透传给 akshare。
- ts 时区:港股 16:00 HKT 收盘 → UTC。

🔴 红线:只读 mock akshare · 不连 CH/PG · 不下单(纯数据源适配单测)。
"""

from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from app.services.data_sources.exceptions import (
    DataFormatError,
    SymbolNotFoundError,
)
from app.services.data_sources.hk_source import AKShareHkSource, _hk_daily_ts


def _fake_hk_df() -> pd.DataFrame:
    """模拟 akshare stock_hk_hist 返回(中文列 · 同 EM 风格)。"""
    return pd.DataFrame({
        "日期": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "开盘": [300.0, 310.0, 305.0],
        "收盘": [305.0, 308.0, 312.0],
        "最高": [312.0, 315.0, 318.0],
        "最低": [298.0, 304.0, 303.0],
        "成交量": [1_000_000.0, 1_200_000.0, 900_000.0],
        "成交额": [3.0e8, 3.6e8, 2.8e8],
    })


def _patch_ak(monkeypatch, df_or_exc) -> dict:
    """patch hk_source.ak.stock_hk_hist · 记录调用参数。返回 captured。"""
    captured: dict = {}

    def _fake(**kwargs):  # noqa: ANN003, ANN202
        captured.update(kwargs)
        if isinstance(df_or_exc, Exception):
            raise df_or_exc
        return df_or_exc

    monkeypatch.setattr(
        "app.services.data_sources.hk_source.ak.stock_hk_hist", _fake,
    )
    return captured


# ===== ts 时区 =====


def test_hk_daily_ts_is_1600_hkt_in_utc():
    """港股 16:00 HKT 收盘 → 08:00 UTC(HKT = UTC+8)。"""
    ts = _hk_daily_ts("2024-01-02")
    assert ts.tzinfo == UTC
    assert ts.hour == 8  # 16:00 HKT = 08:00 UTC
    assert (ts.year, ts.month, ts.day) == (2024, 1, 2)


def test_hk_daily_ts_truncates_time_suffix():
    """日期带时间后缀也容错(取前 10 字符)。"""
    ts = _hk_daily_ts("2024-01-02 00:00:00")
    assert (ts.year, ts.month, ts.day) == (2024, 1, 2)


# ===== fetch_kline 日 / 周线 =====


@pytest.mark.asyncio
async def test_fetch_kline_daily_maps_fields(monkeypatch):
    """日线:中文列正确映射到 Kline · ts 升序 · normalize 代码透传。"""
    captured = _patch_ak(monkeypatch, _fake_hk_df())
    src = AKShareHkSource()
    klines = await src.fetch_kline("700", "1d", limit=10)  # 故意传 3 位,验 normalize

    assert len(klines) == 3
    # akshare 收到规范化的 5 位代码 + daily + qfq
    assert captured["symbol"] == "00700"
    assert captured["period"] == "daily"
    assert captured["adjust"] == "qfq"
    # 字段映射(末根)
    last = klines[-1]
    assert last.open == 305.0
    assert last.close == 312.0
    assert last.high == 318.0
    assert last.low == 303.0
    assert last.volume == 900_000.0
    assert last.amount == 2.8e8
    # ts 升序
    assert [k.ts for k in klines] == sorted(k.ts for k in klines)


@pytest.mark.asyncio
async def test_fetch_kline_weekly_uses_weekly(monkeypatch):
    """周线 1w → akshare period=weekly。"""
    captured = _patch_ak(monkeypatch, _fake_hk_df())
    src = AKShareHkSource()
    await src.fetch_kline("00700", "1w", limit=10)
    assert captured["period"] == "weekly"


@pytest.mark.asyncio
async def test_fetch_kline_limit_tail(monkeypatch):
    """limit 取最近 N 根(tail)。"""
    _patch_ak(monkeypatch, _fake_hk_df())
    src = AKShareHkSource()
    klines = await src.fetch_kline("00700", "1d", limit=2)
    assert len(klines) == 2
    assert klines[-1].close == 312.0  # 最后一根


# ===== 边界 / 异常 =====


@pytest.mark.asyncio
async def test_unsupported_period_raises(monkeypatch):
    """阶段一不支持分钟级 → DataFormatError(不打 akshare)。"""
    _patch_ak(monkeypatch, _fake_hk_df())
    src = AKShareHkSource()
    for p in ("1m", "5m", "15m", "30m", "1h"):
        with pytest.raises(DataFormatError, match="只支持日 / 周线"):
            await src.fetch_kline("00700", p, limit=10)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_empty_df_raises_symbol_not_found(monkeypatch):
    """akshare 返空 → SymbolNotFoundError。"""
    _patch_ak(monkeypatch, pd.DataFrame())
    src = AKShareHkSource()
    with pytest.raises(SymbolNotFoundError):
        await src.fetch_kline("99999", "1d", limit=10)


@pytest.mark.asyncio
async def test_missing_columns_raises_format_error(monkeypatch):
    """字段不全 → DataFormatError。"""
    bad = pd.DataFrame({"日期": ["2024-01-02"], "开盘": [300.0]})  # 缺收盘/最高/...
    _patch_ak(monkeypatch, bad)
    src = AKShareHkSource()
    with pytest.raises(DataFormatError, match="字段不全"):
        await src.fetch_kline("00700", "1d", limit=10)


def test_source_identity():
    """name / market 身份正确(_source_for 映射 + insert market 用)。"""
    src = AKShareHkSource()
    assert src.name == "akshare-hk"
    assert src.market == "hk"
