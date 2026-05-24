"""Worker 启动时确保 ClickHouse 表存在(幂等 · 自包含)· M2-C.2.1。

为什么需要本模块:
    update.sh(部署脚本)只跑 alembic(PostgreSQL 迁移),**没有 ClickHouse 建表
    步骤**。docker/clickhouse-init.sql 只在 CH 容器【首次启动 / 全新数据卷】时由
    /docker-entrypoint-initdb.d 执行;对已存在的 CH 实例,新增表不会自动建。
    每次部署都会 rebuild worker → worker 进程起来时触发 worker_ready 信号 →
    本模块跑 CREATE TABLE IF NOT EXISTS(幂等),零手动步骤,对所有未来 CH 表通用。

红线:只 DDL · 不写业务数据 · 不调任何上游/交易接口。

⚠️ 这里的 DDL 必须与 docker/clickhouse-init.sql 中对应表保持一致(双写不可避免:
   一个给 docker-entrypoint 全新装,一个给 worker 启动幂等 ensure)。
"""

from __future__ import annotations

import logging

import clickhouse_connect

from app.core.config import settings

logger = logging.getLogger(__name__)


# crypto_premium_index · 与 docker/clickhouse-init.sql 保持一致(M2-C.2.1)
_CREATE_PREMIUM_INDEX = """
CREATE TABLE IF NOT EXISTS crypto_premium_index (
    symbol String,
    ts DateTime,
    mark_price Float64,
    index_price Float64,
    last_funding_rate Float64,
    next_funding_time DateTime,
    funding_interval_hours UInt8 DEFAULT 8,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
TTL ingested_at + INTERVAL 7 DAY
SETTINGS index_granularity = 8192
"""

# 未来新增 CH 表 → 往这个 list 里加一条幂等 DDL 即可
_DDL_STATEMENTS: tuple[str, ...] = (_CREATE_PREMIUM_INDEX,)


def ensure_crypto_ch_tables() -> None:
    """worker 启动时幂等建表 · 失败只告警不阻断 worker 启动(行情采集仍可跑)。"""
    try:
        client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
            settings={"session_timezone": "UTC"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ch_schema] 连 ClickHouse 失败 · 跳过建表:%s", exc)
        return
    try:
        for ddl in _DDL_STATEMENTS:
            client.command(ddl)
        logger.info("[ch_schema] crypto CH 表 ensure 完成(%d 条 DDL)", len(_DDL_STATEMENTS))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ch_schema] 建表 DDL 执行失败:%s", exc)
    finally:
        client.close()
