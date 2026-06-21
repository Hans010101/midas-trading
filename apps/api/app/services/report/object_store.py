"""周报素材原始文件对象存储 · ★第三刀-A 桩,第三刀-B 接 oss2 真上传。

设计:把素材原始文件(md/PDF 字节)存阿里云 OSS,prefix `report-materials/`(桶 lifecycle 7 天
过期 · Hans 已配)。素材文本上传时即提取存 DB,生成只读 DB 文本,不回 OSS 下载 → OSS 对象纯归档/审计。

★第三刀-A:不碰 OSS 凭证 → upload_material 不真上传,只 log + 返回 key(DB 存意向键)。
★第三刀-B 接入点(唯一):把 upload_material 的 stub 换成 oss2 实现,键格式/调用方不变 ——
    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)
    await asyncio.to_thread(bucket.put_object, key, data)   # oss2 是同步 SDK → to_thread
    return key
调用方(materials.py)只依赖 build_object_key + upload_material 两接口。
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

# 桶 lifecycle 规则按此 prefix 7 天过期(Hans 已配 · 同 ADR 0042 的 clickhouse/ postgres/ 范式)
OSS_PREFIX = "report-materials"


def build_object_key(*, period_start: date | None, uid: str, ext: str) -> str:
    """素材 OSS 对象键:report-materials/{period_start}/{uuid}{ext}(prefix 命中 lifecycle 规则)。"""
    bucket_day = period_start.isoformat() if period_start else "undated"
    return f"{OSS_PREFIX}/{bucket_day}/{uid}{ext}"


async def upload_material(key: str, data: bytes) -> str:
    """把素材原始文件上传到 OSS · 返回对象键。

    ★第三刀-A:OSS 凭证未就绪 → 不真上传,记 warning,返回 key(DB 存意向键 · B 接后即真实)。
    ★第三刀-B:见模块 docstring 的 oss2 接入示例 —— 只换本函数实现,上游零改动。
    """
    logger.warning(
        "[material] OSS 上传待第三刀-B 接(凭证未就绪)· 仅存意向键 · key=%s · bytes=%d",
        key, len(data),
    )
    return key
