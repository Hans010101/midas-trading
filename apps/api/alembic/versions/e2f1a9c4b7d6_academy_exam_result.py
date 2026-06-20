"""academy_exam_result

训练营 B 期刀2:模块结业测验成绩。每次提交记一条(全历史·可重考)。
纯增量新表,不改任何现有表。

Revision ID: e2f1a9c4b7d6
Revises: b4e7c2a9f1d3
Create Date: 2026-06-19 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2f1a9c4b7d6'
down_revision: str | None = 'b4e7c2a9f1d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'academy_exam_result',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('stage', sa.String(length=16), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column(
            'submitted_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # 按 user+stage 查结业状态 / 最佳分(全历史多行)
    op.create_index(
        'ix_academy_exam_result_user_stage',
        'academy_exam_result',
        ['user_id', 'stage'],
    )


def downgrade() -> None:
    op.drop_index('ix_academy_exam_result_user_stage', table_name='academy_exam_result')
    op.drop_table('academy_exam_result')
