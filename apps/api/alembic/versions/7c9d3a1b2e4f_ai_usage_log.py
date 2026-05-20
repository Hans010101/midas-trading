"""ai_usage_log

0012 · AI 决策卡 LLM 用量日志。

Revision ID: 7c9d3a1b2e4f
Revises: 5a98653dd149
Create Date: 2026-05-20 23:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c9d3a1b2e4f'
down_revision: str | None = '5a98653dd149'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_usage_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('market', sa.String(length=16), nullable=False),
        sa.Column('symbol', sa.String(length=64), nullable=False),
        sa.Column('period', sa.String(length=8), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column(
            'cost_cny', sa.Numeric(precision=10, scale=6),
            nullable=False, server_default=sa.text('0'),
        ),
        sa.Column('node', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text('now()'),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_ai_usage_log_created', 'ai_usage_log', ['created_at'],
    )
    op.create_index(
        'ix_ai_usage_log_symbol_period',
        'ai_usage_log', ['market', 'symbol', 'period'],
    )


def downgrade() -> None:
    op.drop_index('ix_ai_usage_log_symbol_period', table_name='ai_usage_log')
    op.drop_index('ix_ai_usage_log_created', table_name='ai_usage_log')
    op.drop_table('ai_usage_log')
