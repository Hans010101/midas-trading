"""系统健康监控 · Celery beat 每 ~20 分钟查磁盘/ClickHouse 可用空间 · 超阈值 TG 告警 admin。

★背景(2026-07-04 磁盘墙事故):Docker build 缓存(21G 历史死重)+ 镜像堆积撑满 /dev/vda3 →
  ClickHouse 可用空间归 0 → 写不进查不了 → api 500 → 前端"后端不可达"。此任务防复发:提前告警 Hans。
★洞见:ClickHouse 数据与 Docker 缓存同在一块 /dev/vda3 → 查 CH `system.disks.free_space` 既是
  ClickHouse 空间也是【物理磁盘】空间代理(Docker 缓存撑满磁盘时 CH free_space 同步下降 · 正是这次的信号)。
  一个查询覆盖两者 · 且从 worker 直连 CH 无需 SSH / 无需读宿主机 df。
★去抖:同级别告警 1 小时内只发一次(Redis 键 TTL)· 防每 20 分钟刷屏。
★全程 try/except:磁盘满时 CH 可能慢/超时,监控任务【绝不】因此崩 worker(纯卫生任务)。

资源模式对齐 crypto_metrics_ingest:asyncio.run(_async) + clickhouse_connect.get_async_client。
"""

import asyncio
import logging
import os
from typing import Any

import clickhouse_connect
from celery import shared_task
from redis import asyncio as aioredis

from app.core.config import settings
from app.services.notifications import telegram

logger = logging.getLogger(__name__)

# 阈值:磁盘使用率 ≥ 85% 或 可用空间 < 8GB → 告警(任一命中即告警)
DISK_USAGE_WARN_PCT = 85.0
FREE_SPACE_WARN_GB = 8.0
DEBOUNCE_TTL_SEC = 3600  # 同级别告警 1 小时内只发一次
_GB = 1024**3
_ALERT_REDIS_KEY = "monitor:disk_alert:sent"


async def _query_disks() -> list[dict[str, Any]]:
    """查 ClickHouse system.disks · 返回每盘 {name, free_gb, total_gb, used_pct}(CH 与 Docker 同盘)。"""
    ch = await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )
    try:
        result = await ch.query("SELECT name, free_space, total_space FROM system.disks")
    finally:
        await ch.close()

    disks: list[dict[str, Any]] = []
    for name, free_space, total_space in result.result_rows:
        free = int(free_space)
        total = int(total_space)
        used_pct = round((total - free) / total * 100, 1) if total > 0 else 0.0
        disks.append(
            {
                "name": str(name),
                "free_gb": round(free / _GB, 2),
                "total_gb": round(total / _GB, 1),
                "used_pct": used_pct,
            }
        )
    return disks


def _is_over(disk: dict[str, Any]) -> bool:
    return disk["used_pct"] >= DISK_USAGE_WARN_PCT or disk["free_gb"] < FREE_SPACE_WARN_GB


async def _maybe_alert(worst: dict[str, Any]) -> bool:
    """超阈值 → TG 告警 admin(去抖 1 小时)· 返回是否真发。TG 未配置只 log 不阻塞。"""
    if not settings.tg_bot_token or not settings.admin_tg_chat_id:
        logger.warning("磁盘超阈值但 admin TG 未配置(tg_bot_token/admin_tg_chat_id 空):%s", worst)
        return False

    # 去抖:Redis 键 TTL · 同级别 1 小时只发一次(SET NX EX 原子)
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", settings.redis_url), decode_responses=True
    )
    try:
        got = await redis.set(_ALERT_REDIS_KEY, "1", ex=DEBOUNCE_TTL_SEC, nx=True)
    finally:
        await redis.aclose()
    if not got:
        logger.info("磁盘告警去抖命中(1 小时内已发)· 跳过本次:%s", worst)
        return False

    text = (
        "⚠️ *磁盘容量告警* · 点金 Midas\n"
        f"磁盘 `{worst['name']}` 使用率 *{worst['used_pct']}%* · "
        f"可用 *{worst['free_gb']}G* / {worst['total_gb']}G\n"
        f"阈值 ≥{DISK_USAGE_WARN_PCT:.0f}% 或 <{FREE_SPACE_WARN_GB:.0f}G · "
        "请清 Docker 缓存/镜像(`docker builder prune -af` + 旧镜像)防 ClickHouse 写不进。"
    )
    try:
        await telegram.send(settings.tg_bot_token, settings.admin_tg_chat_id, text)
        logger.warning("已发磁盘容量告警到 admin TG:%s", worst)
        return True
    except Exception:
        logger.exception("发磁盘告警到 admin TG 失败")
        return False


async def _check() -> dict[str, Any]:
    disks = await _query_disks()
    if not disks:
        logger.warning("system.disks 返回空 · 无法判磁盘容量")
        return {"ok": False, "reason": "no_disks"}

    over = [d for d in disks if _is_over(d)]
    alerted = False
    worst: dict[str, Any] | None = None
    if over:
        worst = min(over, key=lambda d: d["free_gb"])  # 可用空间最少的盘
        alerted = await _maybe_alert(worst)

    return {"ok": True, "disks": disks, "over": bool(over), "worst": worst, "alerted": alerted}


@shared_task(name="tasks.monitor.check_disk_space")
def check_disk_space() -> dict[str, Any]:
    """Celery 入口 · sync wrapper · 查 CH system.disks 算使用率 → 超阈值告警 admin(去抖)。

    ★纯卫生任务 · 任何异常(CH 慢/超时/网络)只 log 不抛 · 绝不因监控任务本身崩 worker。
    """
    try:
        return asyncio.run(_check())
    except Exception:
        logger.exception("check_disk_space 执行失败(不阻塞 · 下个 beat 会重试)")
        return {"ok": False, "reason": "exception"}
