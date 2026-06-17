"""support_ticket

会员支付工单 / 退款申请表(独立 support 模块)· open → resolved/closed。
🔴 图片不落库(image_count 仅记数量,图走 Resend 附件)· 客服记录长期保留(无激进 TTL)。

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-17 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: str | None = 'e3f4a5b6c7d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'support_ticket',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('contact_email', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('related_order_id', sa.String(length=64), nullable=True),
        sa.Column('image_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=16), server_default='open', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_support_ticket_user_created', 'support_ticket', ['user_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_support_ticket_user_created', table_name='support_ticket')
    op.drop_table('support_ticket')
