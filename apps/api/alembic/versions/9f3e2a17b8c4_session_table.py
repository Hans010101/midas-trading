"""session table

0006 ADR 回归 · JWT → DB session(7天滚动 + 5设备)。

Revision ID: 9f3e2a17b8c4
Revises: 7c9d3a1b2e4f
Create Date: 2026-05-21 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9f3e2a17b8c4'
down_revision: str | None = '7c9d3a1b2e4f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'session',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text('now()'),
        ),
        sa.Column(
            'last_used_at', sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text('now()'),
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['user.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_session_token_hash', 'session', ['token_hash'], unique=True)
    op.create_index(
        'ix_session_user_last_used', 'session', ['user_id', 'last_used_at'],
    )
    op.create_index('ix_session_expires', 'session', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_session_expires', table_name='session')
    op.drop_index('ix_session_user_last_used', table_name='session')
    op.drop_index('ix_session_token_hash', table_name='session')
    op.drop_table('session')
