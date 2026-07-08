"""x_tweet 加 gen_style 列(step1 · 分平台内容生成地基)。

内容生成分平台风格:default=币安广场长文 / x_short=X 短推。存量行 server_default=default 兼容。

Revision ID: s0t1u2v3w4x5
Revises: r9s0t1u2v3w4
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "s0t1u2v3w4x5"
down_revision = "r9s0t1u2v3w4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "x_tweet",
        sa.Column(
            "gen_style", sa.String(length=16), server_default="default", nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("x_tweet", "gen_style")
