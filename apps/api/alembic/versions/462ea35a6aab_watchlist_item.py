"""watchlist_item

Revision ID: 462ea35a6aab
Revises: 1e471a0ea403
Create Date: 2026-05-20 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '462ea35a6aab'
down_revision: str | None = '1e471a0ea403'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'watchlist_item',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('symbol', sa.String(length=64), nullable=False),
        sa.Column('market', sa.String(length=16), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column(
            'added_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'symbol', 'market', name='uq_watchlist_user_symbol',
        ),
    )
    op.create_index(
        'ix_watchlist_user_sort',
        'watchlist_item',
        ['user_id', 'sort_order'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_watchlist_user_sort', table_name='watchlist_item')
    op.drop_table('watchlist_item')
