"""payment_order

Phase 2a 刀1:会员订阅支付订单表(Bcon USDT/BSC)· pending → paid/expired。
external_id unique(不可猜 · 给 Bcon + 回调匹配)· user_id FK · 留多链 chain。

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: str | None = 'd2e3f4a5b6c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'payment_order',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('external_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('plan', sa.String(length=16), nullable=False),
        sa.Column('period', sa.String(length=16), nullable=False),
        sa.Column('amount_usdt', sa.Numeric(20, 8), nullable=False),
        sa.Column('chain', sa.String(length=16), server_default='binance', nullable=False),
        sa.Column('pay_address', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('gateway_txid', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_payment_order_external_id'), 'payment_order', ['external_id'], unique=True,
    )
    op.create_index(
        'ix_payment_order_user_created', 'payment_order', ['user_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_payment_order_user_created', table_name='payment_order')
    op.drop_index(op.f('ix_payment_order_external_id'), table_name='payment_order')
    op.drop_table('payment_order')
