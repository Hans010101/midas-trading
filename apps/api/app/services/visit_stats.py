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


# ═══════════════════════════════════════════════════════════════════════════
# SEO 批6 · 来源归因 + AI 爬虫计数(度量闭环 · docs/seo/2026-07-seo-geo-audit.md D8)
# ═══════════════════════════════════════════════════════════════════════════
# ★D8 隐私口径(相对现有「隐私极简」的一次有意放宽):
#   - 只记【来源域名 hostname】(不记 path — 每篇文章 URL 不同会爆炸且归因价值低)
#     + utm_source 聚合桶 + AI 爬虫 bot 名分桶。
#   - 绝不记 IP / 完整 UA / 个体行为明细。UA 只在前端 middleware 内瞬时分类成 bot 名,
#     UA 字符串本身不离开边缘、不发后端、不落库。
# 与 PV/UV 同款:Redis 实时 HINCRBY(HASH 桶)→ TTL 3 天 → beat flush upsert PG 三表。

_SRC_KEY = "visit:src:{d}"          # HASH: {source_bucket: count}
_REF_KEY = "visit:ref:{d}"          # HASH: {referrer_host: count}
_CRAWLER_KEY = "visit:crawler:{d}"  # HASH: {bot_name: hits}
_REF_HOST_CAP = 500  # referrer host 基数上限(域名天然有界 · 兜底防异常膨胀)

# 精确/后缀域名规则(host == domain 或 host endswith "."+domain)。★用精确匹配而非子串:
# 子串会误吞(如 "t.co" 命中 "reddi**t.co**m"、"x.com" 命中 "netfli**x.co**m")。
# AI 子域(gemini.google.com 等)在此精确命中,先于下方 google 品牌标签兜底 → 归 gemini 不归 google。
_EXACT_RULES: tuple[tuple[str, str], ...] = (
    # ── AI 引擎(GEO 核心归因)──
    ("chat.openai.com", "chatgpt"),
    ("chatgpt.com", "chatgpt"),
    ("perplexity.ai", "perplexity"),
    ("gemini.google.com", "gemini"),
    ("bard.google.com", "gemini"),
    ("copilot.microsoft.com", "copilot"),
    ("claude.ai", "claude"),
    ("kimi.moonshot.cn", "kimi"),
    ("kimi.com", "kimi"),
    ("doubao.com", "doubao"),
    ("metaso.cn", "metaso"),
    ("you.com", "you"),
    ("phind.com", "phind"),
    ("poe.com", "poe"),
    # ── 搜索引擎(单一 TLD · 后缀匹配覆盖子域)──
    ("duckduckgo.com", "duckduckgo"),
    ("so.com", "360"),
    ("ecosia.org", "ecosia"),
    ("brave.com", "brave-search"),
    # ── 社交 / 即时通讯 ──
    ("t.co", "x"),
    ("twitter.com", "x"),
    ("x.com", "x"),
    ("t.me", "telegram"),
    ("telegram.org", "telegram"),
    ("facebook.com", "facebook"),
    ("linkedin.com", "linkedin"),
    ("reddit.com", "reddit"),
    ("weibo.com", "weibo"),
    ("zhihu.com", "zhihu"),
    ("youtube.com", "youtube"),
    ("github.com", "github"),
)

# 品牌标签兜底(多 ccTLD 引擎:google.com / google.com.hk / baidu 移动子域 等)· 在精确规则
# 之后运行,故 gemini.google.com 已先归 gemini · 不被 google 标签误吞。label = 域名中一节。
_LABEL_RULES: tuple[tuple[str, str], ...] = (
    ("google", "google"),
    ("baidu", "baidu"),
    ("bing", "bing"),
    ("yandex", "yandex"),
    ("sogou", "sogou"),
)

# utm_source 归一白名单(投放可信 · 命中即用规范名 · 未命中 → utm:other 防爆炸)
_UTM_CANON: dict[str, str] = {
    "google": "google", "bing": "bing", "baidu": "baidu",
    "chatgpt": "chatgpt", "perplexity": "perplexity", "kimi": "kimi",
    "doubao": "doubao", "gemini": "gemini",
    "twitter": "x", "x": "x", "telegram": "telegram", "tg": "telegram",
    "weibo": "weibo", "zhihu": "zhihu", "newsletter": "newsletter",
    "email": "newsletter", "wechat": "wechat",
}


def _normalize_host(raw: str) -> str:
    """referrer host 归一:小写 · 去 www. 前缀 · 去端口 · 截 120。"""
    h = raw.strip().lower().split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    return h[:120]


def classify_source(
    ref_host: str | None,
    utm_source: str | None = None,
    self_host: str | None = None,
) -> str:
    """把 (referrer host, utm_source) 归到一个固定来源桶 · 纯函数 · 无 IO。

    优先级:utm_source(投放·可信)白名单归一 > ★自有域(internal) > referrer host 规则表 >
    direct(无来源) > referral(有来源但不在表中)。桶集合有界(防 admin 看板维度爆炸)。

    ★self_host(自有公网域·如 midastrade.asia)= Bug A 纵深防御:前端 extractRefHost 已用 Host
      头剔除站内跳转,这里是后端兜底 —— 若前端漏发同域 ref_host(旧缓存/边界),也归 internal
      而非误记 referral(2026-07-07 流量归因诊断:同域 referrer 被误判外部引荐、referral 全自指)。
    """
    if utm_source:
        key = utm_source.strip().lower()[:64]
        if key in _UTM_CANON:
            return _UTM_CANON[key]
        if key:
            return "utm:other"
    if not ref_host or not ref_host.strip():
        return "direct"
    host = _normalize_host(ref_host)
    # ★自有域(站内跳转)→ internal · 不污染 referral(两侧 _normalize_host 对称去 www/端口)
    if self_host and self_host.strip() and host == _normalize_host(self_host):
        return "internal"
    # ① 精确/后缀域名匹配(host == d 或 host 是 d 的子域)
    for domain, bucket in _EXACT_RULES:
        if host == domain or host.endswith("." + domain):
            return bucket
    # ② 品牌标签兜底(google 等多 ccTLD · label 命中)
    labels = host.split(".")
    for label, bucket in _LABEL_RULES:
        if label in labels:
            return bucket
    return "referral"


async def record_source(
    redis: Redis,
    source: str,
    ref_host: str | None,
    day: date_type | None = None,
) -> None:
    """记一次访问的来源桶 + 来源域名(与 record_visit 分离 · 不动 PV/UV 链路)。

    ★只碰 Redis(HINCRBY)· referrer host 基数超上限则跳过新 host(仍计 source 桶)。
    """
    d = day or cn_today()
    sk = _SRC_KEY.format(d=d.isoformat())
    pipe = redis.pipeline()
    pipe.hincrby(sk, source, 1)
    pipe.expire(sk, _KEY_TTL)
    await pipe.execute()

    host = _normalize_host(ref_host) if ref_host else ""
    if not host:
        return
    rk = _REF_KEY.format(d=d.isoformat())
    # 域名天然有界;仅当 host 已存在或未超上限时计数(HEXISTS 一次往返防异常膨胀)
    if await redis.hexists(rk, host) or await redis.hlen(rk) < _REF_HOST_CAP:
        pipe2 = redis.pipeline()
        pipe2.hincrby(rk, host, 1)
        pipe2.expire(rk, _KEY_TTL)
        await pipe2.execute()


async def record_crawler(redis: Redis, bot: str, day: date_type | None = None) -> None:
    """记一次 AI/搜索爬虫访问(bot 名分桶)· 只碰 Redis(HINCRBY)· GEO 领先指标。"""
    d = day or cn_today()
    ck = _CRAWLER_KEY.format(d=d.isoformat())
    pipe = redis.pipeline()
    pipe.hincrby(ck, bot, 1)
    pipe.expire(ck, _KEY_TTL)
    await pipe.execute()


async def _read_hash_day(redis: Redis, key: str) -> dict[str, int]:
    """读某天一个 HASH 桶 → {field: int}(缺失 → {})。

    ★key 强制 str():decode_responses=True 时 redis 返 str,但类型标注是 bytes|str
    (与调用侧 aioredis 客户端配置无关的保守类型)· str() 幂等 · 防 mypy 报 union。
    """
    raw = await redis.hgetall(key)
    return {str(k): int(v) for k, v in raw.items()}


async def read_redis_source_day(redis: Redis, day: date_type) -> dict[str, int]:
    """读某天来源桶实时计数 {source: count}。"""
    return await _read_hash_day(redis, _SRC_KEY.format(d=day.isoformat()))


async def read_redis_referrer_day(redis: Redis, day: date_type) -> dict[str, int]:
    """读某天来源域名计数 {host: count}。"""
    return await _read_hash_day(redis, _REF_KEY.format(d=day.isoformat()))


async def read_redis_crawler_day(redis: Redis, day: date_type) -> dict[str, int]:
    """读某天爬虫计数 {bot: hits}。"""
    return await _read_hash_day(redis, _CRAWLER_KEY.format(d=day.isoformat()))


async def flush_source_recent_days(session: AsyncSession, redis: Redis) -> dict[str, int]:
    """flush 今/昨两天的 来源桶 / 来源域名 / 爬虫 三表(与 PV/UV flush 并列 · 同 beat 调)。

    覆盖语义 upsert(Redis 当日累计 → SET 覆盖,与 flush_day 同哲学)· 空桶跳过不清零。
    """
    from app.models.daily_crawler_stat import DailyCrawlerStat
    from app.models.daily_referrer_stat import DailyReferrerStat
    from app.models.daily_source_stat import DailySourceStat

    today = cn_today()
    out: dict[str, int] = {"source": 0, "referrer": 0, "crawler": 0}
    for d in (today, today - timedelta(days=1)):
        for field, count in (await read_redis_source_day(redis, d)).items():
            await session.execute(
                pg_insert(DailySourceStat)
                .values(date=d, source=field[:120], pv=count)
                .on_conflict_do_update(
                    index_elements=["date", "source"],
                    set_={"pv": count, "updated_at": func.now()},
                ),
            )
            out["source"] += 1
        for field, count in (await read_redis_referrer_day(redis, d)).items():
            await session.execute(
                pg_insert(DailyReferrerStat)
                .values(date=d, referrer=field[:120], pv=count)
                .on_conflict_do_update(
                    index_elements=["date", "referrer"],
                    set_={"pv": count, "updated_at": func.now()},
                ),
            )
            out["referrer"] += 1
        for field, count in (await read_redis_crawler_day(redis, d)).items():
            await session.execute(
                pg_insert(DailyCrawlerStat)
                .values(date=d, bot=field[:120], hits=count)
                .on_conflict_do_update(
                    index_elements=["date", "bot"],
                    set_={"hits": count, "updated_at": func.now()},
                ),
            )
            out["crawler"] += 1
    await session.commit()
    return out
