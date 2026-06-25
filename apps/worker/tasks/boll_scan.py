"""布林做T扫描器 M1(★影子模式)· Celery beat 每 15m bar 收盘后跑。

★影子模式:只把本该推送的【会话级文案】logger.info 打出来,【绝不】调 TG 发送 helper(M2 再翻真)。

🔴 三红线(机器证明钉死):
①绝不接真实下单(纯分析 · 全程无任何 order/trade/execute 调用);
②ClickHouse 只读(klines/tickers 只 select · 状态/冷却只进 Redis,绝不写 CH);
③推送文案经 boll_state.validate_shadow_push 门禁(末尾免责 + 买卖祈使黑名单一票否决)。

数据复用(全部现成,不另造):
- 15m kline:ClickHouseClient.select_kline(纯读 · DESC LIMIT N + reverse)
- 涨跌榜筛选池:clickhouse_crypto.select_latest_tickers(裸 client · change_pct_24h 排序)
- universe:crypto_metrics_ingest._all_usdt_perp_symbols(裸 client · 同 15m 采集口径 Top N)
- Redis 状态/冷却:复用 visit_stats 小时桶范式(set + ex TTL 自动清,不落 PG/CH)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, cast

from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.ai.boll_state import (
    BollSnapshot,
    BollState,
    build_session_message,
    build_transition_digest,
    classify,
    render_card,
    select_for_push,
    state_label,
    to_snapshot_row,
)
from app.services.clickhouse_client import ClickHouseClient
from app.services.clickhouse_crypto import (
    select_latest_funding_rates,
    select_latest_tickers,
)
from app.services.notifications.dott_push import broadcast_dott
from app.services.notifications.events import NotificationKind
from tasks.crypto_metrics_ingest import _all_usdt_perp_symbols

logger = logging.getLogger(__name__)

_UNIVERSE_N = 150          # 扫描标的 = 成交额 Top 150 纯加密永续(同 15m 采集口径)
_POOL_N = 40               # 涨跌榜各取前 40(涨幅 + 跌幅)作推送筛选池(降噪)
_LOOKBACK_BARS = 30        # select_kline 取最近 30 根(布林 20 预热 + 斜率/带宽回看余量)
_STATE_TTL = 24 * 3600     # Redis 状态滚动窗口 ~24h(TTL 自动清)
_COOLDOWN_SEC = 4 * 3600   # 每标的推送冷却 4h(冷却窗口内再转换也不重复推 · 数小时级防同币刷屏)
_SNAPSHOT_KEY = "boll:snapshot:latest"  # ★做T A-1 全量快照(独立 key · 不和边沿状态 key 冲突)
_SNAPSHOT_TTL = 30 * 60                 # 30min 防陈旧(每 15min 刷一次 · 留两轮余量)

# ── M2-1 频率控制(防刷屏 · 参数可调 · 仍影子)─────────────────────────────────
_BATCH_MAX = 5             # 每轮批量上限:转换多时按「信号强度 |%B−0.5|」降序最多取 5 个
_DAILY_MAX = 30            # 每日全局上限:极端行情整天最多 30 条(M2-2 有订阅后细化到用户级)
_DAILY_TTL = 26 * 3600     # 每日计数 key TTL(日界 key 自然换 · 给跨日 buffer)
# ★M2-3b 转换合并:≥2 转换合并成一条简版列表 · 一条最多 _MERGE_MAX 个(超出分多条 · 防超长)·
#   当前 _BATCH_MAX=5 < _MERGE_MAX 故恒不分批,纯防未来调大批量。
_MERGE_MAX = 10


def _state_key(sym: str) -> str:
    return f"boll:state:{sym}"


def _cooldown_key(sym: str) -> str:
    return f"boll:cooldown:{sym}"


def _daily_key() -> str:
    # 全局每日影子推送计数(UTC 日界 · 日期戳 key 自然换天)
    return f"boll:daily:{datetime.now(tz=UTC):%Y%m%d}"


def _prev_label(prev: str) -> str:
    # 转换前状态 → 中文口诀(prev 由本任务自写 · 异常兜底返原值,绝不让一币崩掉整轮)
    try:
        return state_label(BollState(prev))
    except ValueError:
        return prev


async def _boll_scan_async() -> dict[str, int]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    ch = await ClickHouseClient.create()
    # 候选(已过【转换∩涨跌榜∩非冷却】)· (symbol, snap, 转换前口诀)· ★冷却/渲卡延后到批量+每日上限后
    cand: list[tuple[str, BollSnapshot, str]] = []
    snapshot_rows: list[dict[str, Any]] = []  # ★A-1:全量结构快照(每币一行 · 复用 snap)
    universe_n = 0
    transitions = 0
    try:
        # ★裸 client(有 .query)走 ch._client · 同 analysis.py 范式 · 不传 ClickHouseClient 封装类
        universe = (await _all_usdt_perp_symbols(ch._client))[:_UNIVERSE_N]  # noqa: SLF001
        universe_n = len(universe)
        gainers = await select_latest_tickers(
            ch._client, instrument="perp", sort_by="change_pct_24h", order="DESC", limit=_POOL_N,  # noqa: SLF001
        )
        losers = await select_latest_tickers(
            ch._client, instrument="perp", sort_by="change_pct_24h", order="ASC", limit=_POOL_N,  # noqa: SLF001
        )
        pool = {t.symbol.replace("/", "") for t in [*gainers, *losers]}
        # ★A-1:全量 universe 的 24h 涨跌(给快照行用 · 加法,不改上面 pool/edge 口径)
        universe_tickers = await select_latest_tickers(
            ch._client, instrument="perp", sort_by="quote_volume_24h",  # noqa: SLF001
            order="DESC", limit=_UNIVERSE_N,
        )
        change_map = {t.symbol.replace("/", ""): t.change_pct_24h for t in universe_tickers}
        # ★A-2:批量【一次 query】读 universe 最新资金费率(argMax GROUP BY · 读 CH 不去币安)·
        #   读失败降级空 dict(funding 全 None),带宽/布林快照照常落(吸取 ticker 教训:单点不放大)。
        try:
            funding_map = await select_latest_funding_rates(ch._client, symbols=universe)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            logger.warning("[boll-scan] 批量读资金费率失败 · funding 降级 None: %s", exc)
            funding_map = {}

        for sym in universe:
            klines = await ch.select_kline(
                symbol=sym, market="crypto", period="15m", limit=_LOOKBACK_BARS, instrument="perp",
            )
            snap = classify(klines)
            if snap is None:
                continue
            prev = await redis.get(_state_key(sym))
            # 状态滚动窗口(Redis · 不写 CH)· 每轮刷新当前状态
            await redis.set(_state_key(sym), snap.state.value, ex=_STATE_TTL)
            # ★A-1:每个有效币收一行全量快照(复用 snap · 不重算)· 含本轮是否转换。
            #   仅落数据,不参与下面任何边沿/推送/冷却判断 —— M1 逻辑完全不动。
            is_transition = prev is not None and prev != snap.state.value
            snapshot_rows.append(
                to_snapshot_row(
                    sym, snap, change_pct_24h=change_map.get(sym),
                    funding_rate=funding_map.get(sym),
                    # decode_responses=True → redis.get 实为 str|None(stub 误宽成 bytes)
                    transition=is_transition, prev_state=cast("str | None", prev),
                ),
            )
            # 边沿检测:仅【状态发生转换】进候选(无 prev = 冷启动基线,不推)
            if prev is None or prev == snap.state.value:
                continue
            transitions += 1
            if sym not in pool:                          # 降噪:只推涨跌榜前列
                continue
            if await redis.get(_cooldown_key(sym)):      # 每标的冷却(M2-1 冷却时长仍 4h)
                continue
            # ★只收集(不设冷却/不渲卡)· 冷却只对【上限后实际推送的】设,被截断的不冷却 → 下轮仍可竞争
            cand.append((sym, snap, _prev_label(cast("str", prev))))

        # ── M2-1 频率控制:批量上限(按信号强度取最强)+ 每日上限(全局)──────────────
        after_filter = len(cand)                                   # 过【转换∩涨跌榜∩非冷却】后
        daily_count = int(await redis.get(_daily_key()) or 0)
        remaining = max(0, _DAILY_MAX - daily_count)               # 今日全局剩余配额
        batch_n = min(after_filter, _BATCH_MAX)                    # 批量上限截断后的个数
        pushed = select_for_push(cand, batch_max=_BATCH_MAX, daily_remaining=remaining)
        if pushed:
            # ★M2-3b 合并规则(只在 M2-1 筛选输出后加 · 不碰频率控制):
            #   1 个 → 方案B 完整卡(信息全)· ≥2 个 → 简版合并列表一条(超 _MERGE_MAX 分多条)
            if len(pushed) == 1:
                s0, snp0, tf0 = pushed[0]
                msgs = [build_session_message([render_card(s0, snp0, transition_from=tf0)])]
            else:
                msgs = [
                    build_transition_digest(pushed[i : i + _MERGE_MAX])
                    for i in range(0, len(pushed), _MERGE_MAX)
                ]
            # ★冷却 + 每日计数:只对【实际推送的】生效(被上限截掉的不冷却 → 下轮仍可竞争)
            for s, _snp, _tf in pushed:
                await redis.set(_cooldown_key(s), "1", ex=_COOLDOWN_SEC)
            await redis.incrby(_daily_key(), len(pushed))
            await redis.expire(_daily_key(), _DAILY_TTL)
            # ★总闸开 → 真发广播(订阅 dott_transition + 绑 TG + Pro · 安静时段在 dispatch)· 关 → 影子
            if settings.dott_push_live:
                engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
                try:
                    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                        res = await broadcast_dott(db, msgs, kind=NotificationKind.DOTT_TRANSITION)
                finally:
                    await engine.dispose()
                logger.info(
                    "[boll-scan-live] 真发 · %d 转换 → 订阅 %d → 成功 %d 失败 %d 跳过非Pro %d",
                    len(pushed), res.subscribers, res.sent, res.failed, res.skipped_non_pro,
                )
            else:
                for msg in msgs:
                    logger.info(
                        "[boll-scan-shadow] 影子推送文案(★不真发 · 本轮 %d 转换):\n%s",
                        len(pushed), msg,
                    )
        # ★频率漏斗(每轮都打 · 方便验证频率落到合理范围:冷却/批量/每日是否生效)
        logger.info(
            "[boll-scan-throttle] 转换 %d → 候选(涨跌榜∩非冷却) %d → 批量上限取 %d "
            "→ 每日剩余 %d → 本轮影子推送 %d 条",
            transitions, after_filter, batch_n, remaining, len(pushed),
        )

        # ★A-1:落全量结构快照供做T列表接口读 · 独立 key + TTL · ★写失败不影响主流程
        #   (吸取 ticker 教训:单点异常不放大)· 不写 CH、不发 TG、不下单。
        try:
            payload = json.dumps(
                {"as_of": datetime.now(tz=UTC).isoformat(), "items": snapshot_rows},
                ensure_ascii=False,
            )
            await redis.set(_SNAPSHOT_KEY, payload, ex=_SNAPSHOT_TTL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[boll-scan] 落全量快照失败(不影响主流程): %s", exc)

        return {
            "universe": universe_n, "transitions": transitions,
            "after_filter": after_filter,        # 过【转换∩涨跌榜∩非冷却】
            "pushed": len(pushed),               # 批量+每日上限后实际影子推送
            "snapshot": len(snapshot_rows),
        }
    finally:
        await ch.close()
        await redis.aclose()


@shared_task(name="tasks.crypto.boll_scan", max_retries=0)
def boll_scan() -> dict[str, int]:
    """15m bar 收盘后跑 · ★影子模式只打日志不发 TG · 跑现有 midas-worker(concurrency=4 够)。"""
    return asyncio.run(_boll_scan_async())
