"""user google oauth · password_hash 改可空 · 加 google_sub

M1 第三波 · Google OAuth 集成 · 0006 ADR 回归。

Revision ID: d8e2f4a5c7b9
Revises: 9f3e2a17b8c4
Create Date: 2026-05-21 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd8e2f4a5c7b9'
down_revision: str | None = '9f3e2a17b8c4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # password_hash 改可空(OAuth-only 用户无密码)
    op.alter_column(
        'user',
        'password_hash',
        existing_type=sa.String(length=255),
        nullable=True,
    )

    # google_sub:Google `sub` claim · unique 可空 · OAuth 用户登录唯一标识
    op.add_column(
        'user',
        sa.Column('google_sub', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'ix_user_google_sub', 'user', ['google_sub'], unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_user_google_sub', table_name='user')
    op.drop_column('user', 'google_sub')
    op.alter_column(
        'user',
        'password_hash',
        existing_type=sa.String(length=255),
        nullable=False,
    )
