"""academy_exam_award

训练营 B 期刀3:结业测验会员奖励记录。(user_id, stage) UNIQUE → 会员只发一次。
纯增量新表,不改任何现有表。

Revision ID: f5b3c9d1e2a7
Revises: e2f1a9c4b7d6
Create Date: 2026-06-20 01:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5b3c9d1e2a7'
down_revision: str | None = 'e2f1a9c4b7d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'academy_exam_award',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('stage', sa.String(length=16), nullable=False),
        sa.Column(
            'awarded_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # ★ 一个用户一个模块只发一次会员(原子幂等)
        sa.UniqueConstraint('user_id', 'stage', name='uq_academy_exam_award_user_stage'),
    )


def downgrade() -> None:
    op.drop_table('academy_exam_award')
