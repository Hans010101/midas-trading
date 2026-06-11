"""conditional_orders 表 · 条件单挂单簿(ADR 0041 刀1 · 纯新增表 · 可逆)

Revision ID: d7e8f9a0b1c2
Revises: f2a3b4c5d6e7
Create Date: 2026-06-11

═══════════════════════════════════════════════════════════════════════════
限价 / 止损 / 止盈 三类共表(决策一:独立表 · VirtualOrder 二元终态不动)。
状态机 active → triggered / cancelled / expired。挂单不冻结资金(决策二)。
本表不参与撮合 —— 触发成交(刀2)仍走 place_market_order 唯一入口(红线)。

enum:新建 conditional_kind / conditional_status;
     复用现有 order_side / position_side(create_type=False · 照 a1c2e3f4d5b6 先例)。
★ 纯新增表 · 无既有数据 → 低风险、完全可逆(downgrade drop 表 + 仅 drop 两个新 enum)。
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "d7e8f9a0b1c2"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None

# 复用现有 PG enum 类型 · create_type=False(类型已由 0008/3.4 迁移建好,这里只引用)
_ORDER_SIDE = postgresql.ENUM("BUY", "SELL", name="order_side", create_type=False)
_POSITION_SIDE = postgresql.ENUM("LONG", "SHORT", name="position_side", create_type=False)


def upgrade() -> None:
    op.create_table(
        "conditional_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column(
            "order_kind",
            sa.Enum("LIMIT", "STOP_LOSS", "TAKE_PROFIT", name="conditional_kind"),
            nullable=False,
        ),
        sa.Column("side", _ORDER_SIDE, nullable=False),
        sa.Column(
            "position_side", _POSITION_SIDE, nullable=False, server_default="LONG",
        ),
        sa.Column("trigger_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "TRIGGERED", "CANCELLED", "EXPIRED", name="conditional_status"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("triggered_order_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conditional_orders_status_market", "conditional_orders", ["status", "market"],
    )
    op.create_index(
        "ix_conditional_orders_user_created", "conditional_orders", ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conditional_orders_user_created", table_name="conditional_orders")
    op.drop_index("ix_conditional_orders_status_market", table_name="conditional_orders")
    op.drop_table("conditional_orders")
    # 只 drop 本迁移新建的两个 enum(order_side / position_side 是复用,绝不 drop · 照 1476 先例)
    sa.Enum(name="conditional_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="conditional_kind").drop(op.get_bind(), checkfirst=False)
