"""admin_action_log

用户管理刀3b:admin_action_log 通用审计表(grant_pro · 3b-2 封禁复用)。
operator/target ondelete SET NULL → 账号删了审计留痕。

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-06-13 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b0c1d2e3f4a5'
down_revision: str | None = 'a9b0c1d2e3f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'admin_action_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('operator_id', sa.Uuid(), nullable=True),
        sa.Column('target_user_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['operator_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['target_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_action_log_operator_id', 'admin_action_log', ['operator_id'])
    op.create_index('ix_admin_action_log_target_user_id', 'admin_action_log', ['target_user_id'])


def downgrade() -> None:
    op.drop_index('ix_admin_action_log_target_user_id', table_name='admin_action_log')
    op.drop_index('ix_admin_action_log_operator_id', table_name='admin_action_log')
    op.drop_table('admin_action_log')
