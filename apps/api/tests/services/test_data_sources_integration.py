"""三家适配器实拨外网集成测试。

特点:
- 真打 AKShare(Sina) / yfinance / ccxt Binance
- 网络 / 限流 / 服务挂掉时 `pytest.skip`,不让 CI 因为外网原因炸
- 上游回脏数据(如 yfinance 未 finalize 日 bar OHLC 全 NaN → DataFormatError)同属
  「外网原因」→ 同样 skip(2026-06-10 CI 实测翻车:NVDA 2026-06-09 行 NaN 挡了无关分支)
- 验证:K 线非空、ts 升序、OHLC 几何关系、ts 是 tz-aware UTC

只测「日 K + 一只标的」抓最容易出问题的链路;
分钟 K(尤其 AKShare EM 当前不稳)留给 E1 smoke test 跑过即认定通过。
"""

from __future__ import annotations

from datetime import UTC, datetime

import ccxt.async_support as ccxt_async
import pytest

from app.schemas.market import Kline
from app.services.data_sources.cn_source import AKShareCnSource
from app.services.data_sources.crypto_source import CcxtBinanceCryptoSource
from app.services.data_sources.exceptions import DataFormatError, UpstreamUnavailableError
from app.services.data_sources.us_source import YFinanceUsSource


def _assert_klines_valid(rows: list[Kline]) -> None:
    """共用断言:非空 + ts 升序 + ts tz-aware UTC + OHLC 几何。"""
    assert len(rows) > 0
    for i in range(1, len(rows)):
        assert rows[i].ts > rows[i - 1].ts, f"ts 非升序于第 {i} 行"
    for k in rows:
        assert k.ts.tzinfo is not None, "ts 必须 tz-aware"
        assert k.ts.utcoffset() == datetime.now(tz=UTC).utcoffset(), "ts tz 必须是 UTC"
        assert k.low <= k.open <= k.high
        assert k.low <= k.close <= k.high
        assert k.volume >= 0


class TestCnIntegration:
    async def test_real_600519_daily(self) -> None:
        src = AKShareCnSource()
        try:
            rows = await src.fetch_kline("600519", "1d", limit=10)
        except UpstreamUnavailableError as e:
            pytest.skip(f"AKShare Sina 不可达:{e}")
        except DataFormatError as e:
            pytest.skip(f"upstream returned malformed data:{e}")
        _assert_klines_valid(rows)
        # 茅台日 K 价格应在合理量级(几百 ~ 几千元)
        assert 100 < rows[-1].close < 10_000


class TestUsIntegration:
    async def test_real_nvda_daily(self) -> None:
        src = YFinanceUsSource()
        try:
            rows = await src.fetch_kline("NVDA", "1d", limit=10)
        except UpstreamUnavailableError as e:
            pytest.skip(f"yfinance 不可达(可能 IP 451 / 网络):{e}")
        except DataFormatError as e:
            pytest.skip(f"upstream returned malformed data:{e}")
        _assert_klines_valid(rows)
        # NVDA 价格量级
        assert 10 < rows[-1].close < 1_000


class TestCryptoIntegration:
    async def test_real_btc_daily(self) -> None:
        exchange = ccxt_async.binance({"enableRateLimit": True, "timeout": 30_000})
        try:
            src = CcxtBinanceCryptoSource(exchange=exchange)
            try:
                rows = await src.fetch_kline("BTC/USDT", "1d", limit=10)
            except UpstreamUnavailableError as e:
                pytest.skip(f"ccxt Binance 不可达:{e}")
            except DataFormatError as e:
                pytest.skip(f"upstream returned malformed data:{e}")
            _assert_klines_valid(rows)
            assert 1_000 < rows[-1].close < 1_000_000
        finally:
            await exchange.close()
