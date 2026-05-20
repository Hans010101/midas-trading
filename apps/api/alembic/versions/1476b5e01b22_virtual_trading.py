"""virtual_trading

0008 v2 · 4 张表 + 5 个 Enum 类型 · 三独立子账户方案。

Revision ID: 1476b5e01b22
Revises: fff9c29c4c7f
Create Date: 2026-05-20 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1476b5e01b22'
down_revision: str | None = 'fff9c29c4c7f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===== virtual_account =====
    op.create_table(
        'virtual_account',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('market', sa.String(length=16), nullable=False),
        sa.Column(
            'currency',
            sa.Enum('CNY', 'USD', 'USDT', name='currency'),
            nullable=False,
        ),
        sa.Column('initial_capital', sa.Numeric(20, 4), nullable=False),
        sa.Column('cash_balance', sa.Numeric(20, 4), nullable=False),
        sa.Column(
            'realized_pnl',
            sa.Numeric(20, 4),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column(
            'activated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'market', name='uq_virtual_account_user_market',
        ),
    )
    op.create_index(
        'ix_virtual_account_user', 'virtual_account', ['user_id'], unique=False,
    )

    # ===== virtual_position =====
    op.create_table(
        'virtual_position',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=64), nullable=False),
        sa.Column('market', sa.String(length=16), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('avg_entry_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('realized_pnl', sa.Numeric(20, 4), nullable=True),
        sa.Column(
            'opened_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['account_id'], ['virtual_account.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    # partial unique:同账户同标的最多一个活仓
    op.create_index(
        'uq_virtual_position_active',
        'virtual_position',
        ['account_id', 'symbol'],
        unique=True,
        postgresql_where=sa.text('closed_at IS NULL'),
    )
    op.create_index(
        'ix_virtual_position_account_closed',
        'virtual_position',
        ['account_id', 'closed_at'],
        unique=False,
    )

    # ===== virtual_order =====
    op.create_table(
        'virtual_order',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=64), nullable=False),
        sa.Column('market', sa.String(length=16), nullable=False),
        sa.Column(
            'side', sa.Enum('BUY', 'SELL', name='order_side'), nullable=False,
        ),
        sa.Column(
            'order_type',
            sa.Enum('MARKET', name='order_type'),
            server_default='MARKET',
            nullable=False,
        ),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('price', sa.Numeric(20, 8), nullable=True),
        sa.Column('notional', sa.Numeric(20, 4), nullable=True),
        sa.Column('commission', sa.Numeric(20, 4), nullable=True),
        sa.Column('slippage_cost', sa.Numeric(20, 4), nullable=True),
        sa.Column('realized_pnl', sa.Numeric(20, 4), nullable=True),
        sa.Column(
            'status',
            sa.Enum('FILLED', 'REJECTED', name='order_status'),
            nullable=False,
        ),
        sa.Column('reject_reason', sa.String(length=128), nullable=True),
        sa.Column(
            'placed_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['account_id'], ['virtual_account.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_virtual_order_account_placed',
        'virtual_order',
        ['account_id', 'placed_at'],
        unique=False,
    )

    # ===== virtual_equity_snapshot =====
    op.create_table(
        'virtual_equity_snapshot',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('market', sa.String(length=16), nullable=False),
        sa.Column('cash', sa.Numeric(20, 4), nullable=False),
        sa.Column('positions_value', sa.Numeric(20, 4), nullable=False),
        sa.Column('equity', sa.Numeric(20, 4), nullable=False),
        sa.Column('realized_pnl_cumulative', sa.Numeric(20, 4), nullable=False),
        sa.Column(
            'trigger_kind',
            sa.Enum('ORDER_FILLED', 'DAILY', name='snapshot_trigger'),
            nullable=False,
        ),
        sa.Column(
            'snapshot_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['account_id'], ['virtual_account.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_virtual_equity_account_at',
        'virtual_equity_snapshot',
        ['account_id', 'snapshot_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_virtual_equity_account_at', table_name='virtual_equity_snapshot')
    op.drop_table('virtual_equity_snapshot')
    op.drop_index('ix_virtual_order_account_placed', table_name='virtual_order')
    op.drop_table('virtual_order')
    op.drop_index('ix_virtual_position_account_closed', table_name='virtual_position')
    op.drop_index('uq_virtual_position_active', table_name='virtual_position')
    op.drop_table('virtual_position')
    op.drop_index('ix_virtual_account_user', table_name='virtual_account')
    op.drop_table('virtual_account')
    # Drop enum types
    sa.Enum(name='snapshot_trigger').drop(op.get_bind(), checkfirst=False)
    sa.Enum(name='order_status').drop(op.get_bind(), checkfirst=False)
    sa.Enum(name='order_type').drop(op.get_bind(), checkfirst=False)
    sa.Enum(name='order_side').drop(op.get_bind(), checkfirst=False)
    sa.Enum(name='currency').drop(op.get_bind(), checkfirst=False)
