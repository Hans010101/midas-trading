"""invitation_table

Phase 1.5 刀A:invitation 表(归因 pending / 兑现 rewarded_at)。
invitee_id unique = 一人终身一次兑现(防重复)。

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-13 11:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f8a9b0c1d2e3'
down_revision: str | None = 'e7f8a9b0c1d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'invitation',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('inviter_id', sa.Uuid(), nullable=False),
        sa.Column('invitee_id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.String(length=12), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('rewarded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['inviter_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invitee_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invitee_id'),
    )
    op.create_index('ix_invitation_inviter_id', 'invitation', ['inviter_id'])


def downgrade() -> None:
    op.drop_index('ix_invitation_inviter_id', table_name='invitation')
    op.drop_table('invitation')
