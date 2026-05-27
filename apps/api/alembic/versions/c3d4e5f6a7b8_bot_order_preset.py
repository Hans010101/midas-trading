"""bot_order_preset 表 · 0026 G5 bot 下单后台预设(纯新增 · 不碰任何现有表)

Revision ID: c3d4e5f6a7b8
Revises: a7b8c9d0e1f2
Create Date: 2026-05-28

纯新增一张 bot_order_preset 表(per-user · user_id 为 PK + FK→user.id CASCADE)。
不修改 / 不删除任何现有表或列。downgrade 直接 drop 该表(纯新增,可干净回滚,无数据损失)。
默认值与 services/bot/order.py 的 DEFAULT_* 常量一致 —— 老用户无此行时 bot 下单仍走默认(零回归)。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

_TABLE = "bot_order_preset"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "perp_leverage", sa.Integer(),
            server_default=sa.text("3"), nullable=False,
        ),
        sa.Column(
            "perp_notional_usdt", sa.Numeric(precision=20, scale=4),
            server_default=sa.text("100"), nullable=False,
        ),
        sa.Column(
            "perp_margin_mode", sa.String(length=16),
            server_default=sa.text("'isolated'"), nullable=False,
        ),
        sa.Column(
            "spot_notional_cny", sa.Numeric(precision=20, scale=4),
            server_default=sa.text("10000"), nullable=False,
        ),
        sa.Column(
            "spot_notional_usd", sa.Numeric(precision=20, scale=4),
            server_default=sa.text("1000"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    # 纯新增表 · 直接 drop · 无现有数据受影响。
    op.drop_table(_TABLE)
