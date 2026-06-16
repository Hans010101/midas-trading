"""ClickHouse 异步客户端封装。

负责 kline 写入(带去重)、kline 区间查询、symbol_meta 写入。

设计要点:
- 用 clickhouse-connect 的 AsyncClient(已在 pyproject 依赖里)
- 写入前先查已存在的 ts 集合,过滤掉重复行(MergeTree 不自动去重)
- 时区:Kline.ts 是 tz-aware UTC;ClickHouse 的 DateTime 列存 naive,
  写入时去 tz,读出时补回 UTC tz
- amount 列在 CH 是 Float64 非空;None ↔ 0.0(M0 不引入 schema 变更)
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import clickhouse_connect

from app.core.config import settings
from app.schemas.market import Kline, Market, Period, SymbolMeta

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

# CH Date 列非 nullable,SymbolMeta.listed_date 为 None 时用这个哨兵代替
# (CH Date 合法范围起点)。读出时如果是这个值,语义就是「上游未提供」
_LISTED_DATE_UNKNOWN: date = date(1970, 1, 1)

logger = logging.getLogger(__name__)

_KLINE_COLUMNS: tuple[str, ...] = (
    "symbol",
    "market",
    "instrument",   # M2-B · 0017 ADR · 'spot' / 'perp' · 默认 spot 兼容老数据
    "period",
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)

# M2-B · Crypto Pro 合约 K 线用 'perp' · 其它情况用 'spot'
# 当前 spot / perp 只有 crypto market 有意义 · cn/us 永远是 spot
KLINE_INSTRUMENT_DEFAULT = "spot"


def normalize_kline_symbol(symbol: str, market: str, instrument: str) -> str:
    """crypto perp symbol 归一到 Binance 风格无斜杠(刀A2-1 双形态治理)。

    采集任务(update_crypto_demo)与币安回源都写 'BTCUSDT';历史上端点 persist
    用过 'BTC/USDT' → 同 symbol 两套行,前端命中 stale 孤儿(H/USDT 三处三价根因之一)。
    select / insert 内部统一归一 → 所有调用方一次性全修;旧带斜杠 perp 行从此
    无人命中(毒数据 · 物理清理留 A2-2)。crypto spot(ccxt 形态)与股票不动。
    """
    if market == "crypto" and instrument == "perp":
        return symbol.replace("/", "")
    return symbol


_PERIOD_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "1d": 86400, "1w": 604800,
}


def drop_unclosed_klines(rows: list[Kline], period: str) -> list[Kline]:
    """丢弃【当前未收盘】根(ts >= 当前 period 窗口起点)· 只留已收盘根。

    采集"方案 C"关键:写入 kline 的根必须都已收盘(close 已定盘不再变)→ 完美契合
    insert_kline 同 ts 跳过(写过的根永不被覆盖),绕开普通 MergeTree 无法重写当前根的拦路虎。
    binance klines 末根通常是当前未收盘根 · 按窗口边界过滤(比"丢最后一根"更稳,边界时刻不误删)。
    未知 period(不在表)→ 原样返回(保守不丢)。
    """
    secs = _PERIOD_SECONDS.get(period)
    if not secs:
        return rows
    now_epoch = int(datetime.now(tz=UTC).timestamp())
    boundary = now_epoch - (now_epoch % secs)  # 当前窗口起点 epoch · ts >= 此 = 未收盘
    return [r for r in rows if int(r.ts.timestamp()) < boundary]

_SYMBOL_META_COLUMNS: tuple[str, ...] = (
    "symbol",
    "market",
    "name",
    "name_en",
    "listed_date",
    "is_active",
    "updated_at",
)


class ClickHouseClient:
    """ClickHouse 业务层封装。生命周期由 FastAPI lifespan 管理(单例)。"""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    @classmethod
    async def create(cls) -> ClickHouseClient:
        """从 settings 构造并连通 ClickHouse。

        强制 session_timezone='UTC',否则 CH DateTime 列在 naive 写入/读出时
        会以 server 时区(默认跟 docker 容器 TZ 走)做隐式转换,
        Kline.ts 的 UTC 语义会被悄悄破坏。详见 docs/decisions/0002 第 2 条。
        """
        client = await clickhouse_connect.get_async_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            database=settings.clickhouse_database,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            settings={"session_timezone": "UTC"},
        )
        logger.info(
            "ClickHouse 客户端已建立:host=%s port=%s db=%s user=%s",
            settings.clickhouse_host,
            settings.clickhouse_port,
            settings.clickhouse_database,
            settings.clickhouse_user,
        )
        return cls(client)

    async def close(self) -> None:
        await self._client.close()
        logger.info("ClickHouse 客户端已关闭")

    # =====================
    # kline 写 / 读
    # =====================

    async def insert_kline(
        self,
        rows: list[Kline],
        *,
        symbol: str,
        market: Market,
        period: Period,
        instrument: str = KLINE_INSTRUMENT_DEFAULT,
    ) -> int:
        """批量插入 K 线,已存在的 ts 跳过。返回真正新增的行数。

        M2-B(0017 ADR)· 新增 instrument 参数:
          · 'spot' (默认) · 现货 K 线 · cn / us / crypto-spot 都用这个
          · 'perp'        · USDT-M 永续合约 K 线 · 只 crypto 有
          · 现有调用方不传 instrument 时 = 'spot' · 向后兼容
        """
        if not rows:
            return 0
        # 刀A2-1:crypto perp 写入形态归一(与采集任务/币安同形态 · 杜绝双形态再生)
        symbol = normalize_kline_symbol(symbol, market, instrument)

        ts_set_aware_utc = {self._to_aware_utc(r.ts) for r in rows}
        min_ts = min(ts_set_aware_utc)
        max_ts = max(ts_set_aware_utc)

        # 查这段时间窗里已经存在的 ts(同 instrument)· M2-B 增加 instrument 过滤
        existing = await self._client.query(
            "SELECT ts FROM kline "
            "WHERE symbol = %(s)s AND market = %(m)s AND instrument = %(inst)s "
            "AND period = %(p)s AND ts BETWEEN %(min)s AND %(max)s",
            parameters={
                "s": symbol,
                "m": market,
                "inst": instrument,
                "p": period,
                "min": min_ts,
                "max": max_ts,
            },
        )
        # CH SELECT 返回的是 naive datetime,需要补 UTC tz 才能与我们的 aware set 比较
        existing_ts: set[datetime] = {
            row[0].replace(tzinfo=UTC) if row[0].tzinfo is None else row[0]
            for row in existing.result_rows
        }

        new_rows = [r for r in rows if self._to_aware_utc(r.ts) not in existing_ts]
        if not new_rows:
            logger.info(
                "kline 跳过 %d 行重复(symbol=%s market=%s instrument=%s period=%s)",
                len(rows),
                symbol,
                market,
                instrument,
                period,
            )
            return 0

        # 注:_KLINE_COLUMNS 顺序(M2-B 后):symbol, market, instrument, period, ts, ...
        data = [
            (
                symbol,
                market,
                instrument,
                period,
                self._to_aware_utc(r.ts),
                r.open,
                r.high,
                r.low,
                r.close,
                r.volume,
                r.amount if r.amount is not None else 0.0,
            )
            for r in new_rows
        ]
        await self._client.insert(
            "kline",
            data,
            column_names=list(_KLINE_COLUMNS),
        )
        logger.info(
            "kline 新增 %d 行(symbol=%s market=%s instrument=%s period=%s,跳过重复 %d)",
            len(new_rows),
            symbol,
            market,
            instrument,
            period,
            len(rows) - len(new_rows),
        )
        return len(new_rows)

    async def select_kline(
        self,
        *,
        symbol: str,
        market: Market,
        period: Period,
        limit: int = 500,
        since: datetime | None = None,
        instrument: str = KLINE_INSTRUMENT_DEFAULT,
    ) -> list[Kline]:
        """查指定标的 / 周期**最近** `limit` 根 K 线,返回 ts 升序。

        修复(0010 § A):此前用 ORDER BY ts ASC LIMIT N 会取**最早**的 N 根
        (因为 LIMIT 在 ASC 排序后生效)· 现改 DESC LIMIT N(取最新 N 根)+
        Python 端 reverse 保留 ASC 契约。所有 K 线相关调用方语义不变,
        但 limit=1/2 这种小窗口请求(用于 price fetcher / price anomaly)
        终于能拿到真正的「最新价」。

        M2-B(0017 ADR)· 新增 instrument 参数:
          · 'spot' (默认) · 现货 K 线
          · 'perp'        · USDT-M 永续合约 K 线
          · 不传 = 默认 spot · 向后兼容现有调用方
          · 缠论引擎跟工作台直接复用本方法 · 改 instrument 参数即可读 perp

        刀A2-1 两处治理(叠在 0010 之上):
          · symbol 归一:crypto perp 统一无斜杠 → 所有调用方一次性修掉双形态孤儿命中。
          · 同 ts 重复行读端无害化:裸 MergeTree + check-then-insert 并发竞态会留
            重复行(K2)· GROUP BY ts 任取一行(重复 bar 近似等价)· 不物理删(A2-2)。
        """
        # 刀A2-1:crypto perp 查询形态归一(与写入/采集任务同形态)
        symbol = normalize_kline_symbol(symbol, market, instrument)
        sql = (
            "SELECT ts, any(open) AS open, any(high) AS high, any(low) AS low, "
            "any(close) AS close, any(volume) AS volume, any(amount) AS amount "
            "FROM kline "
            "WHERE symbol = %(symbol)s AND market = %(market)s "
            "AND instrument = %(instrument)s AND period = %(period)s"
        )
        params: dict[str, Any] = {
            "symbol": symbol,
            "market": market,
            "instrument": instrument,
            "period": period,
        }
        if since is not None:
            sql += " AND ts >= %(since)s"
            params["since"] = self._to_aware_utc(since)
        # GROUP BY ts 去重(K2 读端无害化)· DESC 拿最新 N 根 · Python 端 reverse 还原 ASC
        sql += " GROUP BY ts ORDER BY ts DESC LIMIT %(limit)s"
        params["limit"] = limit

        result = await self._client.query(sql, parameters=params)
        # DB 返回 ts DESC · Python 端 reverse 还原 ASC(保持调用方契约)
        klines = [
            Kline(
                ts=row[0].replace(tzinfo=UTC),
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
                amount=row[6] if row[6] > 0 else None,
            )
            for row in result.result_rows
        ]
        klines.reverse()
        return klines

    async def symbol_exists(
        self, market: str, symbol: str, instrument: str = KLINE_INSTRUMENT_DEFAULT,
    ) -> bool:
        """轻量存在性探测(SELECT 1 ... LIMIT 1 · 不 SELECT *)· 给 bot 扫库判定市场用。

        symbol 经 normalize_kline_symbol(与 select_kline 同口径:crypto perp 去斜杠 · 其余原样;
        crypto spot 带斜杠 'BTC/USDT' 不变)· 有行即 True。instrument 默认 spot(cn/us 列存在但无关;
        crypto 查 spot)。
        """
        symbol = normalize_kline_symbol(symbol, market, instrument)
        result = await self._client.query(
            "SELECT 1 FROM kline WHERE symbol = %(s)s AND market = %(m)s "
            "AND instrument = %(inst)s LIMIT 1",
            parameters={"s": symbol, "m": market, "inst": instrument},
        )
        return len(result.result_rows) > 0

    async def crypto_ticker_exists(self, ccxt_symbol: str) -> bool:
        """加密币是否在 ticker 全库(crypto_ticker_24h perp · 实时全市场 ~675 币)· bot 加密判据用。

        ccxt_symbol = 'XXX/USDT' 带斜杠(与 ticker 表 symbol 键一致)· 有行即 True。
        ★扩判据:原 symbol_exists 查 spot kline 只 3 币(除 BTC 几乎全漏);ticker 全库 TRX 等都命中。
        """
        result = await self._client.query(
            "SELECT 1 FROM crypto_ticker_24h WHERE symbol = %(s)s "
            "AND instrument = 'perp' LIMIT 1",
            parameters={"s": ccxt_symbol},
        )
        return len(result.result_rows) > 0

    async def latest_kline_ts(
        self,
        *,
        symbol: str,
        market: str,
        period: str,
        instrument: str = KLINE_INSTRUMENT_DEFAULT,
    ) -> datetime | None:
        """某标的/周期 kline 的最新 ts(tz-aware UTC)· 无数据 → None · 给"是否有实时图"判据用。

        symbol 经 normalize_kline_symbol(同 select_kline)· CH max() 空集返 1970,year<2000 视为无。
        """
        symbol = normalize_kline_symbol(symbol, market, instrument)
        result = await self._client.query(
            "SELECT max(ts) FROM kline WHERE symbol = %(s)s AND market = %(m)s "
            "AND instrument = %(inst)s AND period = %(p)s",
            parameters={"s": symbol, "m": market, "inst": instrument, "p": period},
        )
        rows = result.result_rows
        if not rows or rows[0][0] is None:
            return None
        ts: datetime = rows[0][0]
        if ts.year < 2000:  # noqa: PLR2004 · CH max() 对空集返 1970(无数据)
            return None
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)

    async def select_first_kline_at_or_after(
        self,
        *,
        symbol: str,
        market: Market,
        period: Period,
        at_or_after: datetime,
        instrument: str = KLINE_INSTRUMENT_DEFAULT,
    ) -> Kline | None:
        """查 `ts >= at_or_after` 的**最早一根** K 线(ASC LIMIT 1)· 无则 None。

        用途:reflection 回填(0036 批次乙)· 找 AI 分析 horizon 后的首根实测价。

        ★ 红线:只读 CH 已采历史 · 纯 SELECT · 绝不触发实时上游采集。

        为什么不复用 select_kline:select_kline 是 `ORDER BY ts DESC LIMIT N`
        (取最新 N 根 · 0010 教训),用它找「horizon 后首根」需 N 覆盖到 now,小周期
        (1h/5m)gap 大时会被 LIMIT 截断 → 取到偏晚的 K 线 → 错误回填。本方法
        `ASC LIMIT 1` 语义精确、不受窗口大小影响,是「某时刻之后首根」的正确查询。
        """
        result = await self._client.query(
            "SELECT ts, open, high, low, close, volume, amount FROM kline "
            "WHERE symbol = %(symbol)s AND market = %(market)s "
            "AND instrument = %(instrument)s AND period = %(period)s "
            "AND ts >= %(at_or_after)s "
            "ORDER BY ts ASC LIMIT 1",
            parameters={
                "symbol": symbol,
                "market": market,
                "instrument": instrument,
                "period": period,
                "at_or_after": self._to_aware_utc(at_or_after),
            },
        )
        rows = result.result_rows
        if not rows:
            return None
        row = rows[0]
        return Kline(
            ts=row[0].replace(tzinfo=UTC),
            open=row[1],
            high=row[2],
            low=row[3],
            close=row[4],
            volume=row[5],
            amount=row[6] if row[6] > 0 else None,
        )

    async def count_kline(
        self,
        *,
        symbol: str,
        market: Market,
        period: Period,
        instrument: str = KLINE_INSTRUMENT_DEFAULT,
    ) -> int:
        """统计某 symbol/market/instrument/period 当前在 CH 里的 K 线条数,用于诊断缺口。

        M2-B(0017 ADR)· 新增 instrument 参数 · 默认 spot 向后兼容。
        """
        result = await self._client.query(
            "SELECT count() FROM kline "
            "WHERE symbol = %(s)s AND market = %(m)s "
            "AND instrument = %(inst)s AND period = %(p)s",
            parameters={"s": symbol, "m": market, "inst": instrument, "p": period},
        )
        return int(result.result_rows[0][0])

    # =====================
    # symbol_meta 写 / 搜
    # =====================

    async def upsert_symbol_meta(self, metas: list[SymbolMeta]) -> int:
        """upsert symbol_meta(ReplacingMergeTree 按 updated_at 自动覆盖旧版本)。"""
        if not metas:
            return 0
        data = [
            (
                m.symbol,
                m.market,
                m.name,
                m.name_en,
                m.listed_date if m.listed_date is not None else _LISTED_DATE_UNKNOWN,
                1 if m.is_active else 0,
                self._to_aware_utc(m.updated_at),
            )
            for m in metas
        ]
        await self._client.insert(
            "symbol_meta",
            data,
            column_names=list(_SYMBOL_META_COLUMNS),
        )
        logger.info("symbol_meta upsert %d 行", len(metas))
        return len(metas)

    async def search_symbols(
        self,
        *,
        query: str,
        market: Market | None = None,
        limit: int = 50,
    ) -> list[SymbolMeta]:
        """模糊搜索标的(symbol / name / name_en 任一命中)。"""
        sql = (
            "SELECT symbol, market, name, name_en, listed_date, is_active, updated_at "
            "FROM symbol_meta FINAL "
            "WHERE is_active = 1 AND ("
            " positionCaseInsensitive(symbol, %(q)s) > 0"
            " OR positionCaseInsensitive(name, %(q)s) > 0"
            " OR positionCaseInsensitive(name_en, %(q)s) > 0"
            ")"
        )
        params: dict[str, Any] = {"q": query}
        if market is not None:
            sql += " AND market = %(m)s"
            params["m"] = market
        sql += " ORDER BY symbol LIMIT %(limit)s"
        params["limit"] = limit

        result = await self._client.query(sql, parameters=params)
        return [
            SymbolMeta(
                symbol=row[0],
                market=row[1],
                name=row[2],
                name_en=row[3] or "",
                # CH 里存的 _LISTED_DATE_UNKNOWN 视为「未提供」,读出时翻译回 None
                listed_date=(
                    row[4] if row[4] and row[4] != _LISTED_DATE_UNKNOWN else None
                ),
                is_active=bool(row[5]),
                updated_at=row[6].replace(tzinfo=UTC),
            )
            for row in result.result_rows
        ]

    # =====================
    # 工具
    # =====================

    @staticmethod
    def _to_aware_utc(dt: datetime) -> datetime:
        """归一为 tz-aware UTC datetime,传给 clickhouse-connect。

        关键:不要传 naive datetime!clickhouse-connect 会用 OS 本地时区
        (Asia/Shanghai 等)做 astimezone(),naive 会被当本地时间转 UTC,
        导致 8 小时偏移。详见 docs/decisions/0002 第 3 条。
        """
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)  # 契约假设:naive 输入就是 UTC
        return dt.astimezone(UTC)
