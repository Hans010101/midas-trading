"""发布频率守卫(发布层 PR-1)· Redis 计数 · 每平台每日上限 + 最小发帖间隔(★防风控)。

仿做T每日上限范式:date-stamped key 自然跨日重置 · 成功才计入(失败不耗配额)。
★发布是对外发公开内容 · 频率守卫是防平台风控/封号的硬约束,不是可选项。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

# 每平台每日上限(币安广场官方 100 条/天)· 没列的平台不限日额(如 x · 待其规则定)
_DAILY_CAP: dict[str, int] = {"binance_square": 100}
_MIN_INTERVAL_S = 30  # 最小发帖间隔(秒)· 防短时间连发触发风控
_TTL_S = 60 * 60 * 48  # 日计数 key TTL 2 天(自然跨日 + 兜底)


def _daily_key(platform: str) -> str:
    # ★date-stamped(UTC)· 自然跨日重置(同做T boll:daily 范式)
    return f"xpub:daily:{platform}:{datetime.now(tz=UTC).date().isoformat()}"


def _last_key(platform: str) -> str:
    return f"xpub:last:{platform}"


async def check_rate(redis: Any, platform: str) -> tuple[bool, str]:
    """发布前只读检查:超日额 / 太频繁 → (False, 原因);可发 → (True, "")。"""
    cap = _DAILY_CAP.get(platform)
    if cap is not None:
        cnt = int(await redis.get(_daily_key(platform)) or 0)
        if cnt >= cap:
            return False, f"今日已达 {cap} 条上限,明日再发"
    last = await redis.get(_last_key(platform))
    if last is not None and (time.time() - float(last)) < _MIN_INTERVAL_S:
        return False, f"发帖太频繁,请 {_MIN_INTERVAL_S}s 后再试"
    return True, ""


async def record_post(redis: Any, platform: str) -> None:
    """★发布成功才计入(失败不耗配额)· incr 日计数 + 记最近发帖时间。"""
    key = _daily_key(platform)
    await redis.incr(key)
    await redis.expire(key, _TTL_S)
    await redis.set(_last_key(platform), str(time.time()))
