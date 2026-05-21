"""M2-A · 虚拟合约交易 4 张表(只建 schema · M2-C 实装撮合)

Revision ID: a2b3c4d5e6f7
Revises: d8e2f4a5c7b9
Create Date: 2026-05-21 23:30:00 UTC

跟 0017 ADR § 7 一致 · 4 张表:
  · virtual_futures_account            · per user 一个合约账户
  · virtual_futures_position           · 持仓 · per (account, symbol, direction)
  · virtual_futures_order              · 订单(开/平/加/减仓 + 止损止盈)
  · virtual_futures_funding_settlement · 资金费率结算流水

红线:本 migration 只建表 schema · 不实装任何撮合逻辑 · M2-C 实装。
所有交易都是**虚拟资金** · 跟 Binance 真实合约账户无关。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a2b3c4d5e6f7"
down_revision = "d8e2f4a5c7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ========================================================================
    # 1 · virtual_futures_account · per user 一个合约子账户
    # ========================================================================
    op.create_table(
        "virtual_futures_account",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False, unique=True, index=True,
        ),
        sa.Column("initial_capital", sa.Numeric(20, 4), nullable=False),
        sa.Column("wallet_balance", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "cumulative_realized_pnl", sa.Numeric(20, 4),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "cumulative_funding_pnl", sa.Numeric(20, 4),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "margin_mode",
            sa.Enum("cross", "isolated", name="futures_margin_mode_enum"),
            nullable=False, server_default="cross",
        ),
        sa.Column(
            "activated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )

    # ========================================================================
    # 2 · virtual_futures_position · 持仓
    # ========================================================================
    op.create_table(
        "virtual_futures_position",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id", sa.Integer(),
            sa.ForeignKey("virtual_futures_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("long", "short", name="futures_position_direction_enum"),
            nullable=False,
        ),
        sa.Column("leverage", sa.Integer(), nullable=False),
        sa.Column(
            "margin_mode",
            sa.Enum("cross", "isolated", name="futures_margin_mode_enum", create_type=False),
            nullable=False, server_default="cross",
        ),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("initial_margin", sa.Numeric(20, 4), nullable=False),
        sa.Column("maintenance_margin", sa.Numeric(20, 4), nullable=False),
        sa.Column("mark_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(20, 4), nullable=True),
        sa.Column("liq_price", sa.Numeric(20, 8), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_futures_position_account_symbol_dir",
        "virtual_futures_position",
        ["account_id", "symbol", "direction"],
    )

    # ========================================================================
    # 3 · virtual_futures_order
    # ========================================================================
    op.create_table(
        "virtual_futures_order",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id", sa.Integer(),
            sa.ForeignKey("virtual_futures_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column(
            "side",
            sa.Enum("buy", "sell", name="futures_order_side_enum"),
            nullable=False,
        ),
        sa.Column(
            "order_type",
            sa.Enum(
                "market", "limit", "stop_market", "stop_limit",
                "take_profit_market", "take_profit_limit",
                name="futures_order_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("reduce_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("leverage", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=True),
        sa.Column("stop_price", sa.Numeric(20, 8), nullable=True),
        sa.Column(
            "filled_quantity", sa.Numeric(20, 8),
            nullable=False, server_default="0",
        ),
        sa.Column("avg_fill_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("commission", sa.Numeric(20, 4), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(20, 4), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new", "partially_filled", "filled", "canceled", "rejected", "expired",
                name="futures_order_status_enum",
            ),
            nullable=False, server_default="new",
        ),
        sa.Column("reject_reason", sa.String(128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_futures_order_account_status",
        "virtual_futures_order", ["account_id", "status"],
    )
    op.create_index(
        "ix_futures_order_account_symbol_created",
        "virtual_futures_order", ["account_id", "symbol", "created_at"],
    )

    # ========================================================================
    # 4 · virtual_futures_funding_settlement
    # ========================================================================
    op.create_table(
        "virtual_futures_funding_settlement",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id", sa.Integer(),
            sa.ForeignKey("virtual_futures_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "position_id", sa.Integer(),
            sa.ForeignKey("virtual_futures_position.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("funding_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("funding_rate", sa.Numeric(10, 8), nullable=False),
        sa.Column("mark_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("position_qty", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("long", "short", name="futures_position_direction_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("funding_pnl", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_funding_settlement_account_ts",
        "virtual_futures_funding_settlement",
        ["account_id", "funding_ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_funding_settlement_account_ts", table_name="virtual_futures_funding_settlement")
    op.drop_table("virtual_futures_funding_settlement")

    op.drop_index("ix_futures_order_account_symbol_created", table_name="virtual_futures_order")
    op.drop_index("ix_futures_order_account_status", table_name="virtual_futures_order")
    op.drop_table("virtual_futures_order")

    op.drop_index("ix_futures_position_account_symbol_dir", table_name="virtual_futures_position")
    op.drop_table("virtual_futures_position")

    op.drop_table("virtual_futures_account")

    # 删枚举类型(Postgres)
    sa.Enum(name="futures_order_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="futures_order_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="futures_order_side_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="futures_position_direction_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="futures_margin_mode_enum").drop(op.get_bind(), checkfirst=True)
