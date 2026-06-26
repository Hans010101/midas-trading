"""platform_dispatch · X 营销发布层台账(发布层 PR-1)

一推文 × 平台 = 一条发布记录 · 唯一约束 (tweet_id, platform) 幂等防重复发 · 台账永久留存。

Revision ID: c7d8e9f0a1b2
Revises: f7e8d9c0b1a2
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "f7e8d9c0b1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_dispatch",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tweet_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("platform_post_id", sa.String(length=128), nullable=True),
        sa.Column("platform_post_url", sa.String(length=512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("dispatched_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["tweet_id"], ["x_tweet.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dispatched_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        # ★幂等:一推文每平台至多一条
        sa.UniqueConstraint(
            "tweet_id", "platform", name="uq_platform_dispatch_tweet_platform",
        ),
    )
    op.create_index(
        "ix_platform_dispatch_tweet_id", "platform_dispatch", ["tweet_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_dispatch_tweet_id", table_name="platform_dispatch")
    op.drop_table("platform_dispatch")
