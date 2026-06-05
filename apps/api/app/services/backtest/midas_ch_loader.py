"""MidasCHLoader · vibe-trading-ai 0.1.9 路径B 数据源(只读 Midas ClickHouse)。

让 vibe 回测引擎经【路径B】(显式 import 引擎 + 显式传 loader 调 run_backtest)读
Midas 已采进 ClickHouse 的真实行情跑回测。满足 vibe 的 DataLoaderProtocol
(base.py:126):类属性 name/markets/requires_auth + is_available() + fetch()。

★ 只读:全程只 SELECT / EXISTS TABLE,绝不 INSERT / ALTER / 写任何表。
★ 红线:本模块不 import vibe 的 registry / _get_loader / resolve_loader —— 路径B
   显式把本 loader 传给 engine.run_backtest,无外部源 fallback 余地。
★ 凭证:CH 连接只从环境变量读;密码绝不硬编码 / 绝不写默认值 / 绝不打印或记日志。

环境变量(由部署/容器传入):
  CLICKHOUSE_HOST(必填)· CLICKHOUSE_USER(必填)· CLICKHOUSE_PASSWORD(必填)
  CLICKHOUSE_PORT(可选,默认 8123 · HTTP)· CLICKHOUSE_DATABASE(可选,默认 default)
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import clickhouse_connect
import pandas as pd

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client

logger = logging.getLogger(__name__)

# Vibe interval(大小写混合)→ Midas period(小写)。
# Vibe _VALID_INTERVALS = {1m,5m,15m,30m,1H,4H,1D};Midas period = {1m,5m,15m,30m,1h,1d,1w}。
# 仅映射两边重叠子集;不在表内(如 Vibe "4H" —— Midas 无 4h)→ fetch 明确 raise,
# 绝不静默给错周期。Midas 独有的 1w 也收(直接调本 loader 时可用;Vibe config 层不收)。
_INTERVAL_TO_PERIOD: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1H": "1h",
    "1h": "1h",
    "1D": "1d",
    "1d": "1d",
    "1W": "1w",
    "1w": "1w",
}

# crypto quote 后缀:把无斜杠符号(BTCUSDT)拆回带斜杠 CH 符号(BTC/USDT)用。
# 先支持主流稳定币 quote,顺序敏感(长的在前避免 USDT 被 USD 误截)· 留可扩展。
_CRYPTO_QUOTES: tuple[str, ...] = ("USDT", "USDC", "BUSD", "FDUSD", "USD")

_OHLCV_COLUMNS: list[str] = ["open", "high", "low", "close", "volume"]


def _require_env(name: str) -> str:
    """读必填环境变量;缺失 / 空 → 明确 raise(不打印其值)。"""
    val = os.environ.get(name)
    if not val:
        msg = f"MidasCHLoader: 必填环境变量 {name} 未设置(或为空)"
        raise RuntimeError(msg)
    return val


def to_ch_symbol(code: str) -> str:
    """Vibe code → Midas CH 真实符号(crypto perp · 带斜杠)。

    接受 'BTCUSDT' / 'BTC/USDT' / 'BTC-USDT' → 'BTC/USDT'。
    已带斜杠原样返回;无分隔符按已知 quote 后缀拆分;都不匹配则原样返回
    (让 CH 查空 → fetch 明确 raise,而非悄悄查错符号)。crypto 先行,留扩展。
    """
    s = code.strip().upper().replace("-", "/")
    if "/" in s:
        return s
    for quote in _CRYPTO_QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[: -len(quote)]}/{quote}"
    return s


class MidasCHLoader:
    """vibe DataLoaderProtocol 实现 · 只读 Midas ClickHouse 的 crypto perp 行情。"""

    # 路径B 下 name 是纯标签(引擎不查 registry);取 "ccxt" 让万一被市场推断也落 crypto。
    name = "ccxt"
    markets = {"crypto"}
    requires_auth = False

    def __init__(self) -> None:
        # 只从环境变量读;密码无默认、不打印。port / database 给非密默认值(实测 8123 / default)。
        self._host: str = _require_env("CLICKHOUSE_HOST")
        self._user: str = _require_env("CLICKHOUSE_USER")
        self._password: str = _require_env("CLICKHOUSE_PASSWORD")
        self._port: int = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
        self._database: str = os.environ.get("CLICKHOUSE_DATABASE", "default")
        self._client: Client | None = None

    def _connect(self) -> Client:
        """惰性建同步 HTTP 客户端 · session_timezone=UTC(守 docs/decisions/0002 tz 坑)。"""
        client = self._client
        if client is None:
            client = clickhouse_connect.get_client(
                host=self._host,
                port=self._port,
                database=self._database,
                username=self._user,
                password=self._password,
                settings={"session_timezone": "UTC"},
            )
            self._client = client
            # 只记非敏感连接信息;password 绝不入日志。
            logger.info(
                "MidasCHLoader 已连 ClickHouse:host=%s port=%s db=%s user=%s",
                self._host,
                self._port,
                self._database,
                self._user,
            )
        return client

    def is_available(self) -> bool:
        """能连上 CH 且 kline 表存在 → True;否则 False(失败原因记 error,不静默吞)。"""
        try:
            client = self._connect()
            rows = client.query("EXISTS TABLE kline").result_rows
            ok = bool(rows) and int(rows[0][0]) == 1
            if not ok:
                logger.error("MidasCHLoader.is_available:库 %s 无 kline 表", self._database)
            return ok
        except Exception:
            logger.exception("MidasCHLoader.is_available:ClickHouse 不可用")
            return False

    def fetch(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: list[str] | None = None,  # noqa: ARG002 — Protocol 必含;本 loader 不取基本面字段
    ) -> dict[str, pd.DataFrame]:
        """只读 default.kline,返回 {原始 code: df}。

        - df.index = trade_date(DatetimeIndex 升序);列恰为 [open,high,low,close,volume]
          (amount 丢弃)。
        - 返回 dict 的 key 用【与传入 code 完全一致】的形式(传入不带斜杠 → 引擎写
          ohlcv_{code}.csv 不踩 "/" 当路径分隔符的写盘坑)。
        - interval 不在映射表 → ValueError(不静默给错周期)。
        - 某 code 查无数据 → RuntimeError(不返回空 df 让引擎瞎跑)。
        """
        period = _INTERVAL_TO_PERIOD.get(interval)
        if period is None:
            supported = sorted(set(_INTERVAL_TO_PERIOD))
            msg = (
                f"MidasCHLoader:不支持的 interval {interval!r};可映射={supported}。"
                "(Vibe 4H 无对应 Midas period;Midas 无 4h)"
            )
            raise ValueError(msg)

        client = self._connect()
        out: dict[str, pd.DataFrame] = {}
        for code in codes:
            ch_symbol = to_ch_symbol(code)
            rows = client.query(
                "SELECT ts, open, high, low, close, volume FROM kline "
                "WHERE market = 'crypto' AND instrument = 'perp' "
                "AND period = %(period)s AND symbol = %(symbol)s "
                "AND ts >= %(start)s AND ts <= %(end)s "
                "ORDER BY ts ASC",
                parameters={
                    "period": period,
                    "symbol": ch_symbol,
                    "start": start_date,
                    "end": end_date,
                },
            ).result_rows
            if not rows:
                msg = (
                    f"MidasCHLoader:default.kline 查无数据 code={code!r} "
                    f"(ch_symbol={ch_symbol!r} market=crypto instrument=perp "
                    f"period={period} ts∈[{start_date},{end_date}])"
                )
                raise RuntimeError(msg)
            frame = pd.DataFrame(rows, columns=["trade_date", *_OHLCV_COLUMNS])
            frame = frame.set_index("trade_date").sort_index()
            frame.index = pd.DatetimeIndex(frame.index, name="trade_date")
            out[code] = frame[_OHLCV_COLUMNS].astype(float)
        return out

    def close(self) -> None:
        """关闭底层客户端(可选 · harness 用完调,释放 HTTP 连接)。"""
        if self._client is not None:
            self._client.close()
            self._client = None
