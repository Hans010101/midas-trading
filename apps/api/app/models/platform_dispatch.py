"""platform_dispatch · X 营销发布层台账(发布层 PR-1)。

一条 x_tweet → 每个发布平台一条记录(发了哪些平台 / 各自成功失败 / 各自帖子链接)。
★ 唯一约束 (tweet_id, platform):一推文每平台至多一条 → 重发更新同行 → 幂等防重复发(关键防风控)。
★ 台账永久留存(审计外部发了啥)· 不随 x_tweet 的 7天 清理删(清理只删【没有任何 dispatch】的草稿)。
★ 红线:发布永远 admin 显式单次触发,无自动/定时/批量(本表只记录,不驱动任何自动发)。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlatformDispatch(Base):
    """推文 × 平台 发布记录(台账)。"""

    __tablename__ = "platform_dispatch"
    __table_args__ = (
        # ★幂等:一推文每平台至多一条 · 重发走 upsert 更新同行,绝不重复发
        UniqueConstraint("tweet_id", "platform", name="uq_platform_dispatch_tweet_platform"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 已发布推文豁免 7天 清理 → 有 dispatch 的 x_tweet 不会被删,CASCADE 仅理论兜底
    tweet_id: Mapped[int] = mapped_column(
        ForeignKey("x_tweet.id", ondelete="CASCADE"), nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # binance_square / x
    status: Mapped[str] = mapped_column(
        String(16), server_default="pending", nullable=False,  # pending / success / failed
    )
    # ★发布来源(自动托管 PR-1)· manual=后台人工点 · auto=自动托管 · ★server_default 兼容老数据
    source: Mapped[str] = mapped_column(
        String(16), server_default="manual", nullable=False,
    )
    platform_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_post_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 失败原因(含平台错误码)
    # 哪个 admin 点的发布(★取自鉴权,绝不信前端)· 用户删 → SET NULL 保审计行
    dispatched_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
