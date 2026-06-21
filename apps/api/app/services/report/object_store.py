"""周报素材原始文件对象存储 · 第三刀-B 接阿里云 OSS(oss2)。

素材原始文件(md/PDF 字节)存 OSS,prefix `report-materials/`(桶 lifecycle 7 天过期 · Hans 已配)。
素材文本上传时即提取存 DB,生成只读 DB 文本,不回 OSS 下载 → OSS 对象纯归档/审计。

★凭证只从 settings.oss_*(env)读 · 绝不进 git / 日志(只 log key + bytes,不 log 凭证)。
★oss2 是同步 SDK → put_object 走 asyncio.to_thread,不阻塞事件循环。
★凭证缺失 / 上传失败 → 抛 ObjectStoreError(不静默 · 上层端点映射 502)。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# 桶 lifecycle 规则按此 prefix 7 天过期(Hans 已配 · 同 ADR 0042 的 clickhouse/ postgres/ 范式)
OSS_PREFIX = "report-materials"


class ObjectStoreError(Exception):
    """OSS 上传失败 / 凭证未配置(不静默 · 上层端点映射 502)。"""


def build_object_key(*, period_start: date | None, uid: str, ext: str) -> str:
    """素材 OSS 对象键:report-materials/{period_start}/{uuid}{ext}(prefix 命中 lifecycle 规则)。"""
    bucket_day = period_start.isoformat() if period_start else "undated"
    return f"{OSS_PREFIX}/{bucket_day}/{uid}{ext}"


def _bucket() -> Any:
    """oss2 Bucket(凭证从 settings)· 供 _put_object / _get_object 共用。"""
    import oss2  # noqa: PLC0415 · 延迟 import(仅真上传/下载路径需要)

    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    return oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)


def _put_object(key: str, data: bytes) -> None:
    """同步 oss2 put_object(供 asyncio.to_thread 调)· 凭证从 settings 读 · 内网端点。"""
    _bucket().put_object(key, data)


def _get_object(key: str) -> bytes:
    """同步 oss2 get_object(供 asyncio.to_thread 调)· 返回对象字节。"""
    return bytes(_bucket().get_object(key).read())


async def upload_material(key: str, data: bytes) -> str:
    """素材原始文件上传 OSS · 返回对象键。

    ★凭证缺失 → ObjectStoreError(不静默 · 提示 Hans 配 OSS_ACCESS_KEY_ID/SECRET)。
    ★oss2 同步 SDK → to_thread · 上传失败抛 ObjectStoreError(★日志不含凭证)。
    """
    if not (settings.oss_access_key_id and settings.oss_access_key_secret):
        logger.error(
            "[material] OSS 凭证未配置(OSS_ACCESS_KEY_ID/SECRET)· 无法上传 · key=%s", key,
        )
        msg = "OSS 凭证未配置,请检查容器 env"
        raise ObjectStoreError(msg)
    try:
        await asyncio.to_thread(_put_object, key, data)
    except Exception as e:  # noqa: BLE001 · 任何 oss2/网络异常 → 可控错误(不静默)
        logger.exception("[material] OSS 上传失败 key=%s", key)  # ★不打印凭证
        msg = f"OSS 上传失败:{e}"
        raise ObjectStoreError(msg) from e
    logger.info("[material] OSS 上传成功 key=%s bytes=%d", key, len(data))
    return key


async def download_object(key: str) -> bytes:
    """从 OSS 下载对象字节(周报发送取 PDF 附件)· 凭证缺失/下载失败 → ObjectStoreError(不静默)。"""
    if not (settings.oss_access_key_id and settings.oss_access_key_secret):
        logger.error("[material] OSS 凭证未配置 · 无法下载 · key=%s", key)
        msg = "OSS 凭证未配置,请检查容器 env"
        raise ObjectStoreError(msg)
    try:
        data = await asyncio.to_thread(_get_object, key)
    except Exception as e:  # noqa: BLE001
        logger.exception("[material] OSS 下载失败 key=%s", key)
        msg = f"OSS 下载失败:{e}"
        raise ObjectStoreError(msg) from e
    logger.info("[material] OSS 下载成功 key=%s bytes=%d", key, len(data))
    return data
