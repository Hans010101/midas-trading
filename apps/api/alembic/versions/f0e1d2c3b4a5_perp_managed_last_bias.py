"""perp managed last_bias(托管维持的上一次 bias · 信号判平 + 活仓表信号列)

Revision ID: f0e1d2c3b4a5
Revises: c4d5e6f7a8b9
Create Date: 2026-06-28

★nullable 加列(兼容老数据)· 引擎零碰 · 托管编排层维护。
★revision 用 f0e1d2c3b4a5(d5e6f7a8b9c0 已被 currency_enum_to_varchar 占用 · 避碰撞)。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f0e1d2c3b4a5"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "virtual_perp_position",
        sa.Column("last_bias", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("virtual_perp_position", "last_bias")
