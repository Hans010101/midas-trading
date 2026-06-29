"""intelligent_review 复盘历史表(智能交易第二期 PR-8 DeepSeek 复盘生成)

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-06-29

★复盘报告落库(日/周/月)· content=DeepSeek 全文 · review_data=结构化备查 · 唯一(period,period_start)幂等。
🔴只读交易数据生成的分析报告 · 不碰交易执行(旁观分析师)· 与引擎完全解耦。
★revision 选 k2l3m4n5o6p7(grep 确认 0 命中 · 避连续碰撞教训 docs/decisions/0010)。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "k2l3m4n5o6p7"
down_revision = "j1k2l3m4n5o6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligent_review",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("period", sa.String(length=8), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("trade_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("review_data", postgresql.JSONB(), nullable=False),
        sa.Column("is_mock", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "period", "period_start", name="uq_intelligent_review_period_start",
        ),
    )
    # ★存 1 月清理用 created_at 索引(worker 按 created_at < now-30d 删)
    op.create_index(
        "ix_intelligent_review_created_at", "intelligent_review", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_intelligent_review_created_at", table_name="intelligent_review")
    op.drop_table("intelligent_review")
