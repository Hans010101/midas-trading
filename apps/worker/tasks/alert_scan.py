"""告警规则扫描 worker · 0025 G2b / 0028 N1 边沿触发降噪。

beat 每 1 分钟跑一次:遍历所有启用规则 → 按指标分类做频率分层(DP6:价格/技术
每分钟、衍生/全局 5min、市场结构 3min、缠论 30min)→ engine 求值(只读 ClickHouse,
不打实时上游)→ 经【边沿触发去重】决定是否派发 → 经 G2a 核心层 dispatch 推送统一 bot。

🔴 0028 N1 边沿触发(降噪根治):
- Redis state key `alert_rule:state:{rule_id}` · 持久态(无 TTL)· 取值 'triggered' / 'not_triggered'
- 状态机(4 种过渡):
  · not_triggered/missing → triggered:**edge fire**(过 cooldown 护栏后派发,成功则写 state=triggered + 写 cool key)
  · triggered → not_triggered:**状态复位**(写 state=not_triggered,不推)
  · 持续 triggered:不推(已在触发中)
  · 持续 not_triggered:不推
- Cooldown key `alert_rule:cool:{rule_id}` · TTL=cooldown_sec · 仅在 edge fire 派发成功时写
  · 用作"防 mark 抖动跨阈值反复"的护栏 · 即使值刚 not_triggered 又 triggered,cooldown 内仍被压住

🔴 红线:本期【只动去重层 + 写状态】· 不改 evaluate_rule 求值逻辑一行(算得对不对不动)。

与 price_alerts(±5% 自选异动)并存(DP13 + DP9):price_alerts 也改边沿触发。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

import clickhouse_connect
from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.alert_rule import AlertRule
from app.services.alerts.engine import evaluate_rule
from app.services.alerts.registry import ScanContext, get_indicator
from app.services.clickhouse_client import ClickHouseClient
from app.services.notifications.dispatcher import dispatch
from app.services.notifications.events import AlertTriggeredEvent

logger = logging.getLogger(__name__)

# DP6 频率分层:指标分类 → 扫描间隔(分钟)。每分钟 beat,按 epoch 分钟整除判定是否「到点」。
_CATEGORY_INTERVAL_MIN: dict[str, int] = {
    "price": 1,
    "volume": 1,
    "technical": 1,
    "market_structure": 3,
    "crypto_deriv": 5,
    "crypto_global": 5,
    "chan": 30,  # 缠论现算重 · 低频(DP6)
}


def _due(category: str, now: datetime) -> bool:
    interval = _CATEGORY_INTERVAL_MIN.get(category, 1)
    return int(now.timestamp() // 60) % interval == 0


async def _get_ch_raw():  # noqa: ANN202
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )


@shared_task(name="tasks.alerts.scan_alert_rules")
def scan_alert_rules() -> int:
    return asyncio.run(_scan_async())


async def _scan_async() -> int:
    now = datetime.now(tz=UTC)
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    ch = await ClickHouseClient.create()
    raw = await _get_ch_raw()
    triggered = 0
    try:
        ctx = ScanContext(ch=ch, raw=raw)
        async with session_maker() as db:
            result = await db.execute(
                select(AlertRule).where(AlertRule.enabled.is_(True)),
            )
            rules = list(result.scalars().all())
            for rule in rules:
                indicator = get_indicator(rule.indicator)
                if indicator is None or not _due(indicator.category, now):
                    continue
                try:
                    ev = await evaluate_rule(ctx, rule)
                except Exception as e:  # noqa: BLE001 · 单规则失败不致命
                    logger.warning("[alert] rule=%s 求值失败:%s", rule.id, e)
                    continue
                # 0028 N1 边沿触发去重 · curr_state 由本轮求值决定
                # ev.triggered=True 且 value 有效 → 当前处于触发态;否则视为未触发
                curr_state = (
                    "triggered" if (ev.triggered and ev.value is not None) else "not_triggered"
                )
                state_key = f"alert_rule:state:{rule.id}"
                prev_state = await redis.get(state_key)  # str | None(首次=None=unknown)

                # 状态复位:triggered → not_triggered · 写状态不推
                if prev_state == "triggered" and curr_state == "not_triggered":
                    await redis.set(state_key, "not_triggered")
                    continue
                # 持续态(prev==curr,或 prev=None/not_triggered + curr=not_triggered)· 不操作
                if curr_state != "triggered" or prev_state == "triggered":
                    continue

                # 此处:curr_state == "triggered" 且 prev_state != "triggered" → edge fire 候选
                # Cooldown 护栏:即使是 edge,仍受 cooldown_sec 压制(防 mark 抖动反复跨阈值)
                cool_key = f"alert_rule:cool:{rule.id}"
                if await redis.get(cool_key):
                    continue

                event = AlertTriggeredEvent(
                    market=rule.market, symbol=rule.symbol,
                    indicator_label=indicator.label, operator=rule.operator,
                    threshold=float(rule.threshold), value=ev.value,
                    unit=indicator.unit,
                )
                disp = await dispatch(db, rule.user_id, event)
                if disp.any_sent:
                    # 派发成功:更新 state + 写 cool 护栏
                    await redis.set(state_key, "triggered")
                    await redis.set(cool_key, "1", ex=rule.cooldown_sec)
                    triggered += 1
                elif disp.dropped_quiet:
                    # quiet 时段拦截:吞掉但视为"用户已知"(quiet 语义 = 静默,不是延迟)。
                    # 写 state=triggered 防止后续每轮反复空转 dispatcher · 离开 quiet 后
                    # 不补推这一次(若值仍在区间,只有"再次 not_triggered→triggered"才推)。
                    await redis.set(state_key, "triggered")
                # else:dispatch 失败(网络/未绑定/kind disabled)· 不写 state · 下次重试
    finally:
        await ch.close()
        await raw.close()
        await redis.aclose()
        await engine.dispose()

    if triggered:
        logger.info("[alert] 本轮触发 %d 条告警", triggered)
    return triggered
