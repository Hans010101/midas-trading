"""访问统计 · Redis 实时计数 + PG 按天聚合(网站访问看板)。

埋点链路(性能红线:请求路径只碰 Redis,绝不在此写 PG):
  Next 中间件(服务端 · 非浏览器 JS)→ 内网 fire-and-forget POST /api/v1/track/visit
  → record_visit():visit:pv:{date} INCR(PV)· visit:uv:{date} SADD vid → SCARD(当日精确 UV 去重)。
  · 一次 pipeline 往返(O(1) · 亚毫秒)· 两 key TTL 3 天(flush 落库后即可弃,防 Redis 无限增长)。
flush:Celery beat 每 10 分钟 → flush_recent_days() 读 Redis 今/昨 → upsert daily_visit_stat。
读:看板 admin 端点读 PG(历史)+ 叠加 Redis 今/昨(实时,不等下次 flush)。

UV 去重口径:当日精确(Redis SET · 100% 去重,非 HLL 近似)。规模放大后可切 PFADD/PFCOUNT
(固定 ~12KB/天 · ~0.81% 误差),早期低流量用精确 SET。
隐私:只存匿名 visitor_id(随机 · 无身份信息)+ 按天计数;不存 IP / UA / 路径明细。
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_visit_stat import DailyVisitStat

# 看板自然日口径 = CN 本地(与 Celery beat timezone Asia/Shanghai 一致)
CN_TZ = ZoneInfo("Asia/Shanghai")

_PV_KEY = "visit:pv:{d}"
_UV_KEY = "visit:uv:{d}"
_KEY_TTL = 3 * 24 * 3600  # 3 天 · flush 落库后即可弃

# 当天 24 小时分布(运营看高峰时段)· ★纯 Redis、当天临时、TTL 自动清,不落 PG(不建表/不迁移)。
# 历史天小时分布无需回溯(看板只看「当天」),TTL 2 天足够(覆盖跨午夜边界)。
_PV_HOUR_KEY = "visit:pv:{d}:{h}"
_UV_HOUR_KEY = "visit:uv:{d}:{h}"
_HOUR_KEY_TTL = 2 * 24 * 3600  # 2 天 · 当天图用完即弃


def cn_now() -> datetime:
    return datetime.now(CN_TZ)


def cn_today() -> date_type:
    return cn_now().date()


def _pv_key(d: date_type) -> str:
    return _PV_KEY.format(d=d.isoformat())


def _uv_key(d: date_type) -> str:
    return _UV_KEY.format(d=d.isoformat())


def _pv_hour_key(d: date_type, h: int) -> str:
    return _PV_HOUR_KEY.format(d=d.isoformat(), h=h)


def _uv_hour_key(d: date_type, h: int) -> str:
    return _UV_HOUR_KEY.format(d=d.isoformat(), h=h)


async def record_visit(
    redis: Redis,
    visitor_id: str,
    day: date_type | None = None,
    hour: int | None = None,
) -> None:
    """记一次页面访问 · 只碰 Redis(PV INCR + UV SADD)· 单次 pipeline 往返。

    visitor_id 已由调用方裁剪(≤64 · 匿名随机)。绝不写 PG / 绝不阻塞。
    ★同时记当天小时分布(visit:pv|uv:{d}:{h})· day/hour 缺省取 CST 当下(测试可显式传)。
    """
    now = cn_now()
    d = day or now.date()
    h = hour if hour is not None else now.hour
    pk, uk = _pv_key(d), _uv_key(d)
    hpk, huk = _pv_hour_key(d, h), _uv_hour_key(d, h)
    pipe = redis.pipeline()
    pipe.incr(pk)
    pipe.expire(pk, _KEY_TTL)
    pipe.sadd(uk, visitor_id)
    pipe.expire(uk, _KEY_TTL)
    # 当天小时桶(同一 pipeline · 一次往返)
    pipe.incr(hpk)
    pipe.expire(hpk, _HOUR_KEY_TTL)
    pipe.sadd(huk, visitor_id)
    pipe.expire(huk, _HOUR_KEY_TTL)
    await pipe.execute()


async def read_redis_hours(redis: Redis, day: date_type) -> list[tuple[int, int]]:
    """读某天 24 小时 (pv, uv) 分布 · 一次 pipeline(24 GET + 24 SCARD)· 缺失小时 →(0, 0)。

    返回 list[24] · 索引 = 小时 0-23(CST)· uv=SCARD(该小时精确去重)。
    """
    pipe = redis.pipeline()
    for h in range(24):
        pipe.get(_pv_hour_key(day, h))
        pipe.scard(_uv_hour_key(day, h))
    raw = await pipe.execute()
    # raw 顺序:[pv0, uv0, pv1, uv1, ...]
    return [(int(raw[2 * h] or 0), int(raw[2 * h + 1] or 0)) for h in range(24)]


async def read_redis_day(redis: Redis, day: date_type) -> tuple[int, int]:
    """读某天 Redis 实时 (pv, uv)· uv=SCARD(精确去重)· key 不存在 →(0, 0)。"""
    pipe = redis.pipeline()
    pipe.get(_pv_key(day))
    pipe.scard(_uv_key(day))
    pv_raw, uv = await pipe.execute()
    return int(pv_raw or 0), int(uv or 0)


async def flush_day(session: AsyncSession, redis: Redis, day: date_type) -> tuple[int, int]:
    """把某天 Redis 当前快照 upsert 进 daily_visit_stat。

    Redis 计数是【当日累计】(INCR/SADD 累加),故 SET pv=<redis>(覆盖,非自增)即可,
    随当日推进每次 flush 写入更大值,日终最后一次 flush captured 全天。
    若 Redis 该天为空(已过期 / 无访问)→ 跳过,不把已有 PG 行清零。
    """
    pv, uv = await read_redis_day(redis, day)
    if pv == 0 and uv == 0:
        return 0, 0
    stmt = (
        pg_insert(DailyVisitStat)
        .values(date=day, pv=pv, uv=uv)
        .on_conflict_do_update(
            index_elements=[DailyVisitStat.date],
            set_={"pv": pv, "uv": uv, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
    await session.commit()
    return pv, uv


async def flush_recent_days(session: AsyncSession, redis: Redis) -> dict[str, tuple[int, int]]:
    """flush 今/昨两天(覆盖午夜边界:昨日最后增量需一次收尾 flush)。"""
    today = cn_today()
    out: dict[str, tuple[int, int]] = {}
    for d in (today, today - timedelta(days=1)):
        out[d.isoformat()] = await flush_day(session, redis, d)
    return out
