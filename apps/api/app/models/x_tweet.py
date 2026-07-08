"""每日推文(x_tweet · X 营销阶段4a)· admin 生成 AI 技术分析推文 + 门禁结果 + 截图 → 待发(draft)。

★与周报 weekly_dispatch 平行,但职责更轻:状态止于 draft(待发);发布(posted/failed)留阶段4b 等 X API。
★24h 临时存储:created_at 超 24h 由清理 beat 删行 + 删截图文件(image_path)· 无唯一约束(一天可多条)。
★门禁不过的也存(compliance_passed=false + reason),后台可见但 4b 不可发(只发 passed=true 的)。
红线:仅虚拟 · 纯展示 · 影子(4a 无任何 X API 调用)。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class XTweet(Base):
    """单条每日推文记录 · 一币一条(一天可多条 · 无唯一约束)· 24h 临时。"""

    __tablename__ = "x_tweet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    bias: Mapped[str] = mapped_column(String(8), nullable=False)  # 偏多 / 偏空 / 中性
    tweet_text: Mapped[str] = mapped_column(Text, nullable=False)  # 推文(含 #币种 #点金Midas 标签)
    # 截图本地共享卷路径(PR-4 截图模块填 · 在此之前为 NULL)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    compliance_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # 门禁否决原因(compliance_passed=false 时记;通过则 NULL)
    compliance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # draft(待发)· 阶段4b 加 posted(已发)/ failed(发送失败)
    status: Mapped[str] = mapped_column(String(16), server_default="draft", nullable=False)
    # ★自动起草标记(频率调整)· True=自动起草(待补发素材 + 计入 30 配额)· server_default 兼容老数据
    auto_drafted: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False,
    )
    # ★内容生成风格/平台(step1 分平台地基)· default=币安广场长文 / x_short=X 短推 ·
    #   server_default 兼容老数据(存量行=default)· 将来头条/小红书加枚举值即扩展。
    gen_style: Mapped[str] = mapped_column(
        String(16), server_default="default", nullable=False,
    )
    # 触发生成的 admin(删 admin 置空)
    generated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
