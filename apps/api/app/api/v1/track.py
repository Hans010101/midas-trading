"""访问埋点 ingest · Next 中间件(服务端)beacon 调用,记 PV/UV 到 Redis。

★ 非浏览器直调:由 web 容器的 Next 中间件经内网 fire-and-forget POST(见 web/middleware.ts)。
   公开端点(无登录)· 只 bump Redis 计数器(O(1))· 不写 PG · 不回任何敏感数据。
   隐私:只收匿名 visitor_id(随机)· 不记 IP / UA / 路径明细。
   轻量防滥用:若配置 settings.track_ingest_secret,要求 header x-track-secret 匹配,否则静默忽略。
   埋点绝不 load-bearing:任何异常都吞掉返回 204(中间件 fire-and-forget,不影响页面)。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, Response, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.redis_client import get_redis
from app.services.visit_stats import (
    classify_source,
    record_crawler,
    record_source,
    record_visit,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/track", tags=["track"])


class VisitBeacon(BaseModel):
    visitor_id: str = Field(min_length=1, max_length=64)
    # SEO 批6:来源归因(全可选 · 老 payload {visitor_id} 仍合法 · 向后兼容)。
    # ★D8:只收来源【域名 hostname】+ utm_source(前端已剥 path/query)· 绝不收 IP/UA。
    ref_host: str | None = Field(default=None, max_length=120)
    utm_source: str | None = Field(default=None, max_length=64)


class CrawlerBeacon(BaseModel):
    bot: str = Field(min_length=1, max_length=64)  # 前端依 UA 瞬时分类的 bot 名(UA 本身不发)


@router.post("/visit", status_code=status.HTTP_204_NO_CONTENT)
async def track_visit(
    beacon: VisitBeacon,
    x_track_secret: Annotated[str | None, Header()] = None,
) -> Response:
    secret = settings.track_ingest_secret
    if secret and x_track_secret != secret:
        # 配了密钥但不匹配 → 静默忽略(不计数 · 不报错暴露存在性)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        redis = await get_redis()
        await record_visit(redis, beacon.visitor_id.strip()[:64])
        # SEO 批6:来源桶 + 来源域名(与 PV/UV 分离 · 独立 Redis HASH · 不影响上面链路)
        if beacon.ref_host or beacon.utm_source:
            source = classify_source(beacon.ref_host, beacon.utm_source)
            await record_source(redis, source, beacon.ref_host)
    except Exception:  # noqa: BLE001 — 埋点绝不影响主流程
        logger.warning("track_visit 记录失败(忽略)", exc_info=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/crawler", status_code=status.HTTP_204_NO_CONTENT)
async def track_crawler(
    beacon: CrawlerBeacon,
    x_track_secret: Annotated[str | None, Header()] = None,
) -> Response:
    """AI/搜索爬虫访问计数(GEO 领先指标)· 前端 middleware 依 UA 分类后调 · UA 不落库。"""
    secret = settings.track_ingest_secret
    if secret and x_track_secret != secret:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        redis = await get_redis()
        await record_crawler(redis, beacon.bot.strip()[:64])
    except Exception:  # noqa: BLE001 — 埋点绝不影响主流程
        logger.warning("track_crawler 记录失败(忽略)", exc_info=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
