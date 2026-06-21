"""周报素材服务(第三刀-A)· 提取文本 + 存库 + 拉本期 + 注入文本 + 清理。

上传:md/PDF 字节 → 提取文本(md 直读 / PDF pypdf)→ object_store 存原始文件(A 桩)→ 存库。
生成:build_materials_text 拉本期素材 → ★每份截断 + 总预算守卫(超限丢最大并 log,不静默)→ 拼接。
清理:cleanup_expired_materials 删 N 天前行(OSS 对象靠桶 lifecycle 过期 · app 不删 OSS)。

★本期口径:created_at ≥ 报告周期起点(= 本周报回看窗 7 天内上传的素材)· 比精确 period 等值匹配更稳
   (避免「上传日 ≠ 生成日」导致周期错位漏素材)· period_start/end 列仅作展示标记。
"""

from __future__ import annotations

import io
import logging
import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_material import ReportMaterial
from app.services.report.object_store import build_object_key, upload_material

logger = logging.getLogger(__name__)

# 中文 ≈ 0.6 token/字(DeepSeek 口径)· 估算偏保守取 0.7 防低估
_TOKENS_PER_CHAR = 0.7
# 单份素材文本上限(≈ 8.4k tokens)· 截断防单份过长挤爆上下文
_PER_MATERIAL_CHAR_CAP = 12_000
# 注入总预算(≈ 80k tokens · 128K 上下文留足输出 + 平台数据 + prompt)
_TOTAL_TOKEN_BUDGET = 80_000
RETENTION_DAYS = 7  # 素材保留 7 天(DB 行清理 + OSS lifecycle 同口径)

_MD_TYPES = {"text/markdown", "text/x-markdown", "text/plain"}
_PDF_TYPES = {"application/pdf"}
_MD_EXT = {".md", ".markdown", ".txt"}
_PDF_EXT = {".pdf"}


class MaterialExtractError(Exception):
    """素材文本提取失败(损坏 / 不支持的类型)。"""


def _classify(filename: str, content_type: str | None) -> tuple[str, str]:
    """→ (kind: md|pdf, ext)· 扩展名优先(content_type 不可靠)· 不支持抛 MaterialExtractError。"""
    lower = filename.lower()
    ext = lower[lower.rfind(".") :] if "." in lower else ""
    if ext in _PDF_EXT or content_type in _PDF_TYPES:
        return "pdf", ".pdf"
    if ext in _MD_EXT or content_type in _MD_TYPES:
        return "md", ext or ".md"
    msg = f"不支持的素材类型(仅 md / pdf):{filename}"
    raise MaterialExtractError(msg)


def extract_text(filename: str, content_type: str | None, data: bytes) -> tuple[str, str]:
    """提取素材纯文本 → (kind, text)· md 直读 UTF-8;PDF pypdf;失败/空抛 MaterialExtractError。"""
    kind, _ext = _classify(filename, content_type)
    if kind == "md":
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            msg = "md 文件为空"
            raise MaterialExtractError(msg)
        return "md", text

    # PDF:pypdf 提取(损坏 / 扫描件不崩,抛 MaterialExtractError 让上层 422)
    from pypdf import PdfReader  # noqa: PLC0415 · 延迟 import(仅 PDF 路径需要)

    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as e:  # noqa: BLE001 · 任何 pypdf 解析异常都兜底为可控错误
        msg = f"PDF 提取失败(文件可能损坏):{e}"
        raise MaterialExtractError(msg) from e
    if not text:
        msg = "PDF 提取为空(可能是扫描件 / 图片型 PDF · 无文本层)"
        raise MaterialExtractError(msg)
    return "pdf", text


async def create_material(
    session: AsyncSession,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    period_start: date | None,
    period_end: date | None,
    uploaded_by: UUID | None,
) -> ReportMaterial:
    """提取文本 → 存 OSS(A 桩)→ 存 report_material 行。提取失败抛 MaterialExtractError。"""
    kind, text = extract_text(filename, content_type, data)
    uid = uuid_lib.uuid4().hex
    ext = ".pdf" if kind == "pdf" else ".md"
    key = build_object_key(period_start=period_start, uid=uid, ext=ext)
    await upload_material(key, data)  # ★A:桩(返回 key)· B:真上传 OSS

    material = ReportMaterial(
        oss_key=key,
        filename=filename[:255],
        content_type=kind,
        size=len(data),
        extracted_text=text,
        char_count=len(text),
        period_start=period_start,
        period_end=period_end,
        uploaded_by=uploaded_by,
    )
    session.add(material)
    await session.commit()
    await session.refresh(material)
    return material


def _period_floor(period_start: date | None, now: datetime) -> datetime:
    """本期起点 datetime(UTC)· 无周期则回退「近 RETENTION_DAYS 天」。"""
    if period_start is None:
        return now - timedelta(days=RETENTION_DAYS)
    return datetime(period_start.year, period_start.month, period_start.day, tzinfo=UTC)


async def list_materials(
    session: AsyncSession, *, period_start: date | None, now: datetime | None = None,
) -> list[ReportMaterial]:
    """列本期素材(created_at ≥ 本期起点)· created_at 倒序。"""
    now = now or datetime.now(tz=UTC)
    since = _period_floor(period_start, now)
    rows = await session.execute(
        select(ReportMaterial)
        .where(ReportMaterial.created_at >= since)
        .order_by(ReportMaterial.created_at.desc()),
    )
    return list(rows.scalars().all())


async def get_material(session: AsyncSession, material_id: int) -> ReportMaterial | None:
    return await session.get(ReportMaterial, material_id)


async def delete_material(session: AsyncSession, material_id: int) -> bool:
    """删一份素材行(返回是否存在)· OSS 对象靠 lifecycle,此处不删 OSS。"""
    material = await session.get(ReportMaterial, material_id)
    if material is None:
        return False
    await session.delete(material)
    await session.commit()
    return True


async def build_materials_text(
    session: AsyncSession, *, period_start: date | None, now: datetime | None = None,
) -> str:
    """拉本期素材 extracted_text → ★每份截断 + 总预算守卫(超限丢最大并 log)→ 拼接。

    无素材 → 返回空串(生成端优雅降级,只用平台数据)。
    """
    now = now or datetime.now(tz=UTC)
    since = _period_floor(period_start, now)
    rows = (
        await session.execute(
            select(ReportMaterial)
            .where(ReportMaterial.created_at >= since)
            .order_by(ReportMaterial.created_at),
        )
    ).scalars().all()
    if not rows:
        return ""

    # ① 每份截断(单份 cap)· (filename, text, est_tokens)
    items: list[tuple[str, str, int]] = []
    for r in rows:
        text = r.extracted_text or ""
        if len(text) > _PER_MATERIAL_CHAR_CAP:
            text = text[:_PER_MATERIAL_CHAR_CAP] + "\n…[已截断]"
        est = int(len(text) * _TOKENS_PER_CHAR)
        items.append((r.filename, text, est))

    # ② 总预算守卫:超预算反复丢「估算 token 最大」的素材(★log 丢了什么,不静默)
    dropped: list[str] = []
    total = sum(it[2] for it in items)
    while total > _TOTAL_TOKEN_BUDGET and len(items) > 1:
        idx = max(range(len(items)), key=lambda i: items[i][2])
        gone = items.pop(idx)
        dropped.append(gone[0])
        total -= gone[2]
    if dropped:
        logger.warning(
            "[material] 素材注入超 token 预算 → 丢弃 %d 份最大素材(保留 %d 份 · 约 %d tokens):%s",
            len(dropped), len(items), total, dropped,
        )

    blocks = [f"【素材:{it[0]}】\n{it[1]}" for it in items]
    return "\n\n".join(blocks)


async def cleanup_expired_materials(
    session: AsyncSession, *, before: datetime | None = None, now: datetime | None = None,
) -> int:
    """删 before(默认 now-RETENTION_DAYS)之前创建的素材行 · 返回删除行数。

    ★只清 DB 行;OSS 对象由桶 lifecycle(report-materials/ 7 天)自动过期,app 不删 OSS。
    """
    now = now or datetime.now(tz=UTC)
    before = before or (now - timedelta(days=RETENTION_DAYS))
    result = await session.execute(
        delete(ReportMaterial).where(ReportMaterial.created_at < before),
    )
    await session.commit()
    return int(cast("Any", result).rowcount or 0)
