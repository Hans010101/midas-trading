"""周报素材(report_material)· 第三刀。

admin 上传外部搜集的 md / PDF 素材 → 提取文本存库 → 周报生成时按周期注入 prompt。
原始文件存 OSS(第三刀-B 接 oss2 · 桶 lifecycle 7 天自动过期);DB 行由 Celery beat 清 7 天前。

★第三刀-A:oss_key 存【意向键】(object_store stub 算好键但暂不真上传 · B 接 PutObject 到该键);
   extracted_text 在上传时即提取存库(生成只读 DB 文本,不回 OSS 下载)。

🔴 不碰交易 / 收款 / 引擎 · 纯素材文本 + 元数据。素材关联报告口径 = 按周期(本期素材本期用)。
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportMaterial(Base):
    """周报素材行 · md / PDF 提取文本 + OSS 对象键 + 周期标记。"""

    __tablename__ = "report_material"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # OSS 对象键(report-materials/{period}/{uuid}{ext})· 第三刀-A 存意向键,B 接真上传
    oss_key: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # md | pdf(规整后的类型标识 · 非原始 MIME)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # 提取的纯文本(md 直读 / PDF pypdf 提取)· 生成时注入 prompt 的来源
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # 报告周期标记(本期素材本期用)· 上传时按当前周报周期填
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 上传者 admin(删 admin 置空不连带删素材)
    uploaded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        # 生成「拉本期素材」+ 清理「删 7 天前」均按 created_at;列表按周期
        Index("ix_report_material_created", "created_at"),
        Index("ix_report_material_period", "period_start", "period_end"),
    )
