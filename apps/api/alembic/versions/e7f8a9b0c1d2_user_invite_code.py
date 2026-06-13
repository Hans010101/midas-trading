"""user_invite_code

Phase 1.5 刀A:user.invite_code(8 位 Crockford base32 · lazy 生成于首次
GET /invite/me,存量用户零回填 · nullable unique)。

Revision ID: e7f8a9b0c1d2
Revises: c6d7e8f9a0b1
Create Date: 2026-06-13 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: str | None = 'c6d7e8f9a0b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('user', sa.Column('invite_code', sa.String(length=12), nullable=True))
    op.create_unique_constraint('uq_user_invite_code', 'user', ['invite_code'])


def downgrade() -> None:
    op.drop_constraint('uq_user_invite_code', 'user', type_='unique')
    op.drop_column('user', 'invite_code')
