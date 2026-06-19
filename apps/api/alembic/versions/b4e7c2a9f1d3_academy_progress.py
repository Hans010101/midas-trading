"""academy_progress

训练营 B 期刀1:学习进度追踪。一行 = 某用户标记学完某篇文章。
(user_id, article_slug) 唯一 → 重复标记幂等。纯增量新表,不改任何现有表。

Revision ID: b4e7c2a9f1d3
Revises: a7d3e9f1b2c4
Create Date: 2026-06-19 13:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4e7c2a9f1d3'
down_revision: str | None = 'a7d3e9f1b2c4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'academy_progress',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('article_slug', sa.String(length=32), nullable=False),
        sa.Column('stage', sa.String(length=16), nullable=False),
        sa.Column(
            'completed_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # 同一用户同一篇只一条 → 重复标记幂等(端点 ON CONFLICT 的冲突目标)
        sa.UniqueConstraint(
            'user_id', 'article_slug', name='uq_academy_progress_user_article',
        ),
    )
    # 按用户查全部进度(GET /academy/progress)的索引
    op.create_index(
        'ix_academy_progress_user_id', 'academy_progress', ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_academy_progress_user_id', table_name='academy_progress')
    op.drop_table('academy_progress')
