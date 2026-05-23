"""perp_virtual_trading

ADR-0019 v2 · M2-C.1 · 加密永续合约虚拟交易 2 张表 + 4 个新 enum 类型。

- virtual_perp_position · 合约持仓(单向净持仓 · 逐仓)
- virtual_perp_order    · 合约订单流水(不可变)

复用:
- FK → virtual_account.id(0008 crypto USDT 钱包 · D1 共用)
- order_status enum(0008 已建 · 用 create_type=False 引用,不重建)

🔴 红线:只建 schema · 撮合/强平逻辑在 perp_engine · 全程虚拟资金,绝不接真实下单。

Revision ID: c9f1e2d3b4a5
Revises: d8e2f4a5c7b9
Create Date: 2026-05-23 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f1e2d3b4a5"
down_revision: str | None = "d8e2f4a5c7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===== virtual_perp_position =====
    op.create_table(
        "virtual_perp_position",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "side", sa.Enum("LONG", "SHORT", name="perp_side"), nullable=False,
        ),
        sa.Column(
            "margin_mode",
            sa.Enum("ISOLATED", name="margin_mode"),
            server_default="ISOLATED",
            nullable=False,
        ),
        sa.Column("leverage", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("initial_margin", sa.Numeric(20, 4), nullable=False),
        sa.Column("maintenance_margin_rate", sa.Numeric(10, 6), nullable=False),
        sa.Column("liquidation_price", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "realized_pnl",
            sa.Numeric(20, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "fee_paid",
            sa.Numeric(20, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "funding_paid",
            sa.Numeric(20, 4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "close_reason",
            sa.Enum("MANUAL", "LIQUIDATED", "RESET", name="perp_close_reason"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["virtual_account.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # 单向净持仓(D6):同账户同 symbol 最多一个活仓 · partial unique
    op.create_index(
        "uq_perp_position_active",
        "virtual_perp_position",
        ["account_id", "symbol"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index(
        "ix_perp_position_account_closed",
        "virtual_perp_position",
        ["account_id", "closed_at"],
        unique=False,
    )
    # 强平 worker 扫活仓 · 按 symbol 取 mark 比对
    op.create_index(
        "ix_perp_position_active_symbol",
        "virtual_perp_position",
        ["symbol", "closed_at"],
        unique=False,
    )

    # ===== virtual_perp_order =====
    op.create_table(
        "virtual_perp_order",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT",
                name="perp_action",
            ),
            nullable=False,
        ),
        sa.Column("leverage", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=True),
        sa.Column("notional", sa.Numeric(20, 4), nullable=True),
        sa.Column("margin_delta", sa.Numeric(20, 4), nullable=True),
        sa.Column("fee", sa.Numeric(20, 4), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(20, 4), nullable=True),
        # 复用 0008 已建的 order_status 类型 · 不重建(create_type=False)
        sa.Column(
            "status",
            postgresql.ENUM(
                "FILLED", "REJECTED", name="order_status", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("reject_reason", sa.String(length=128), nullable=True),
        sa.Column(
            "is_liquidation",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "placed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"], ["virtual_account.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_perp_order_account_placed",
        "virtual_perp_order",
        ["account_id", "placed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_perp_order_account_placed", table_name="virtual_perp_order")
    op.drop_table("virtual_perp_order")
    op.drop_index(
        "ix_perp_position_active_symbol", table_name="virtual_perp_position",
    )
    op.drop_index(
        "ix_perp_position_account_closed", table_name="virtual_perp_position",
    )
    op.drop_index("uq_perp_position_active", table_name="virtual_perp_position")
    op.drop_table("virtual_perp_position")
    # 只 drop 本 migration 新建的 enum 类型 · 不碰 0008 的 order_status
    sa.Enum(name="perp_close_reason").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="perp_action").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="margin_mode").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="perp_side").drop(op.get_bind(), checkfirst=False)
