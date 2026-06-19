"""daily_visit_stat

网站访问看板:按天聚合 PV/UV 一行/天(date 唯一)· 不存每条访问明细。
实时计数在 Redis,Celery beat 每 10 分钟 flush 进此表。

Revision ID: a7d3e9f1b2c4
Revises: a5b6c7d8e9fa
Create Date: 2026-06-19 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7d3e9f1b2c4'
down_revision: str | None = 'a5b6c7d8e9fa'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'daily_visit_stat',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('pv', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('uv', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column(
            'created_at',
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
        sa.PrimaryKeyConstraint('id'),
    )
    # date 唯一索引(模型 unique=True, index=True 的等价物 · 按天 upsert 的冲突目标)
    op.create_index('ix_daily_visit_stat_date', 'daily_visit_stat', ['date'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_daily_visit_stat_date', table_name='daily_visit_stat')
    op.drop_table('daily_visit_stat')
