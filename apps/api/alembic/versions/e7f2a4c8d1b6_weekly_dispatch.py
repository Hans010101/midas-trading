"""weekly_dispatch · 周报投递(上传成品 → 定时发送)

纯增量新表(weekly_dispatch · 一周一条 year+week 唯一)· 不改任何现有表 · 不碰 market_report(AI 生成保留)。

Revision ID: e7f2a4c8d1b6
Revises: d4a8e1c6b9f2
Create Date: 2026-06-21 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f2a4c8d1b6"
down_revision: str | None = "d4a8e1c6b9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weekly_dispatch",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("pdf_oss_key", sa.String(length=512), nullable=False),
        sa.Column("pdf_filename", sa.String(length=255), nullable=False),
        sa.Column("md_text", sa.Text(), nullable=False),
        sa.Column("extracted", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="uploaded", nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["uploaded_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("year", "week", name="uq_weekly_dispatch_year_week"),
    )


def downgrade() -> None:
    op.drop_table("weekly_dispatch")
