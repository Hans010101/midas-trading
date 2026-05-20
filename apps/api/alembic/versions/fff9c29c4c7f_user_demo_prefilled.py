"""user_demo_prefilled

加 user.demo_prefilled 布尔列(默认 False),
用于 0007 watchlist lazy-fill 仅触发一次(用户主动清空后不再回填)。

Revision ID: fff9c29c4c7f
Revises: 462ea35a6aab
Create Date: 2026-05-20 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'fff9c29c4c7f'
down_revision: str | None = '462ea35a6aab'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'user',
        sa.Column(
            'demo_prefilled',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('user', 'demo_prefilled')
