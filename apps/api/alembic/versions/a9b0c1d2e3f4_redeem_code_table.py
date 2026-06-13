"""redeem_code_table

兑换码模块刀1:redeem_code 表(管理员生成 → 用户兑换开 pro 权益)。
created_by/redeemed_by ondelete SET NULL → nullable(账号删了码仍可追溯/兑换)。

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-13 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9b0c1d2e3f4'
down_revision: str | None = 'f8a9b0c1d2e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'redeem_code',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=12), nullable=False),
        sa.Column('period', sa.String(length=16), nullable=False),
        sa.Column('days', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=128), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('redeemed_by', sa.Uuid(), nullable=True),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['redeemed_by'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('ix_redeem_code_code', 'redeem_code', ['code'])


def downgrade() -> None:
    op.drop_index('ix_redeem_code_code', table_name='redeem_code')
    op.drop_table('redeem_code')
