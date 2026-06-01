"""港股数据源 AKShareHkSource pytest · ADR 0034a P1-2 + yfinance 降级(方案A)。

覆盖(全 mock · 不打真实上游):
- akshare 成功 → 用 akshare(不降级)· 中文列映射 + ts 16:00 HKT 收盘。
- ★ 降级:akshare 失败(连接/空/字段不全)→ 自动走 yfinance(Yahoo)· 代码映射 00700→0700.HK。
- 两源都空 → SymbolNotFound;两源都连接失败 → 503(UpstreamUnavailable)。
- yfinance ts 对齐 akshare(16:00 HKT)· 防 CH 两源各存一行。
- 不支持周期(1m…)→ DataFormatError(不降级)。

🔴 红线:只读 mock(akshare + yfinance)· 不连 CH/PG · 不下单(纯数据源适配单测)。
"""

from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from app.services.data_sources.exceptions import (
    DataFormatError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)
from app.services.data_sources.hk_source import AKShareHkSource, _hk_daily_ts


def _fake_ak_df() -> pd.DataFrame:
    """模拟 akshare stock_hk_hist(中文列 · 3 行)。"""
    return pd.DataFrame({
        "日期": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "开盘": [300.0, 310.0, 305.0],
        "收盘": [305.0, 308.0, 312.0],
        "最高": [312.0, 315.0, 318.0],
        "最低": [298.0, 304.0, 303.0],
        "成交量": [1_000_000.0, 1_200_000.0, 900_000.0],
        "成交额": [3.0e8, 3.6e8, 2.8e8],
    })


def _fake_yf_df() -> pd.DataFrame:
    """模拟 yfinance .history(tz-aware HKT index · 2 行 · 英文列)。"""
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"]).tz_localize("Asia/Hong_Kong")
    return pd.DataFrame(
        {
            "Open": [300.0, 310.0],
            "High": [312.0, 315.0],
            "Low": [298.0, 304.0],
            "Close": [305.0, 308.0],
            "Volume": [1_000_000.0, 1_200_000.0],
        },
        index=idx,
    )


def _patch_ak(monkeypatch, df_or_exc) -> dict:
    captured: dict = {}

    def _fake(**kwargs):  # noqa: ANN003, ANN202
        captured.update(kwargs)
        if isinstance(df_or_exc, Exception):
            raise df_or_exc
        return df_or_exc

    monkeypatch.setattr("app.services.data_sources.hk_source.ak.stock_hk_hist", _fake)
    return captured


class _FakeYfTicker:
    def __init__(self, df_or_exc) -> None:
        self._d = df_or_exc

    def history(self, **_kwargs):  # noqa: ANN003, ANN202
        if isinstance(self._d, Exception):
            raise self._d
        return self._d


def _patch_yf(monkeypatch, df_or_exc) -> dict:
    captured: dict = {}

    def _ticker(code):  # noqa: ANN001, ANN202
        captured["code"] = code
        return _FakeYfTicker(df_or_exc)

    monkeypatch.setattr("app.services.data_sources.hk_source.yf.Ticker", _ticker)
    return captured


# ===== ts 时区 =====


def test_hk_daily_ts_is_1600_hkt_in_utc():
    """港股 16:00 HKT 收盘 → 08:00 UTC。"""
    ts = _hk_daily_ts("2024-01-02")
    assert ts.tzinfo == UTC
    assert ts.hour == 8
    assert (ts.year, ts.month, ts.day) == (2024, 1, 2)


# ===== akshare 主源成功(不降级)=====


@pytest.mark.asyncio
async def test_akshare_success_no_fallback(monkeypatch):
    """akshare 成功 → 用 akshare(3 行)· yfinance 不被调用。"""
    ak_cap = _patch_ak(monkeypatch, _fake_ak_df())
    yf_cap = _patch_yf(monkeypatch, _fake_yf_df())  # patch 但不应被调
    src = AKShareHkSource()
    ks = await src.fetch_kline("700", "1d", limit=10)  # 3 位验 normalize
    assert len(ks) == 3
    assert ak_cap["symbol"] == "00700"
    assert ak_cap["adjust"] == "qfq"
    assert ks[-1].close == 312.0
    assert "code" not in yf_cap  # ★ akshare 成功 · 没降级 yfinance


@pytest.mark.asyncio
async def test_akshare_weekly(monkeypatch):
    """周线走 akshare period=weekly。"""
    ak_cap = _patch_ak(monkeypatch, _fake_ak_df())
    _patch_yf(monkeypatch, _fake_yf_df())
    src = AKShareHkSource()
    await src.fetch_kline("00700", "1w", limit=10)
    assert ak_cap["period"] == "weekly"


# ===== ★ 降级 yfinance =====


@pytest.mark.asyncio
async def test_fallback_akshare_connection_fail_to_yfinance(monkeypatch):
    """★ akshare 连接失败(生产场景 RemoteDisconnected)→ 自动降级 yfinance 采到。"""
    _patch_ak(monkeypatch, ConnectionError("RemoteDisconnected"))
    yf_cap = _patch_yf(monkeypatch, _fake_yf_df())
    src = AKShareHkSource()
    ks = await src.fetch_kline("00700", "1d", limit=10)
    assert len(ks) == 2  # yfinance 2 行
    assert yf_cap["code"] == "0700.HK"  # ★ 代码映射 00700→0700.HK
    assert ks[-1].close == 308.0
    # ts 对齐 akshare(16:00 HKT = 08:00 UTC)· 不是 yfinance 原始午夜
    assert ks[0].ts.hour == 8
    assert ks[0].ts.tzinfo == UTC


@pytest.mark.asyncio
async def test_fallback_akshare_empty_to_yfinance(monkeypatch):
    """akshare 返空 → 降级 yfinance(09988→9988.HK)。"""
    _patch_ak(monkeypatch, pd.DataFrame())
    yf_cap = _patch_yf(monkeypatch, _fake_yf_df())
    src = AKShareHkSource()
    ks = await src.fetch_kline("09988", "1d", limit=10)
    assert len(ks) == 2
    assert yf_cap["code"] == "9988.HK"


@pytest.mark.asyncio
async def test_fallback_akshare_bad_columns_to_yfinance(monkeypatch):
    """akshare 字段不全(协议变)→ 降级 yfinance 救场。"""
    _patch_ak(monkeypatch, pd.DataFrame({"日期": ["2024-01-02"], "开盘": [300.0]}))
    _patch_yf(monkeypatch, _fake_yf_df())
    src = AKShareHkSource()
    ks = await src.fetch_kline("00700", "1d", limit=10)
    assert len(ks) == 2  # 降级救场


# ===== 两源都失败 =====


@pytest.mark.asyncio
async def test_both_empty_raises_symbol_not_found(monkeypatch):
    """akshare 失败 + yfinance 空 → SymbolNotFound。"""
    _patch_ak(monkeypatch, ConnectionError("x"))
    _patch_yf(monkeypatch, pd.DataFrame())
    src = AKShareHkSource()
    with pytest.raises(SymbolNotFoundError):
        await src.fetch_kline("00700", "1d", limit=10)


@pytest.mark.asyncio
async def test_both_connection_fail_raises_503(monkeypatch):
    """akshare + yfinance 都连接失败 → UpstreamUnavailable(503)。"""
    _patch_ak(monkeypatch, ConnectionError("east money down"))
    _patch_yf(monkeypatch, ConnectionError("yahoo down"))
    src = AKShareHkSource()
    with pytest.raises(UpstreamUnavailableError):
        await src.fetch_kline("00700", "1d", limit=10)


# ===== 代码映射 / 周期 / 身份 =====


def test_to_yf_code_mapping():
    """akshare 5 位 → yfinance ticker(去前导0补4位+.HK)。"""
    assert AKShareHkSource._to_yf_code("00700") == "0700.HK"  # noqa: SLF001
    assert AKShareHkSource._to_yf_code("09988") == "9988.HK"  # noqa: SLF001
    assert AKShareHkSource._to_yf_code("00005") == "0005.HK"  # noqa: SLF001
    assert AKShareHkSource._to_yf_code("700") == "0700.HK"  # noqa: SLF001 · 容错 3 位


@pytest.mark.asyncio
async def test_unsupported_period_raises_no_fallback(monkeypatch):
    """不支持周期 → DataFormatError(两源都只日/周 · 不降级、不打任何源)。"""
    _patch_ak(monkeypatch, _fake_ak_df())
    _patch_yf(monkeypatch, _fake_yf_df())
    src = AKShareHkSource()
    for p in ("1m", "5m", "15m", "30m", "1h"):
        with pytest.raises(DataFormatError, match="只支持日 / 周线"):
            await src.fetch_kline("00700", p, limit=10)  # type: ignore[arg-type]


def test_source_identity():
    src = AKShareHkSource()
    assert src.name == "akshare-hk"
    assert src.market == "hk"
