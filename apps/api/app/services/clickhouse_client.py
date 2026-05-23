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
        """
        sql = (
            "SELECT ts, open, high, low, close, volume, amount FROM kline "
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
        # DESC 拿最新 N 根 · Python 端再 reverse 还原 ASC
        sql += " ORDER BY ts DESC LIMIT %(limit)s"
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
