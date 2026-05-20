"""notification_config

0009 · 推送通知 · per user lazy create.

Revision ID: 5a98653dd149
Revises: 1476b5e01b22
Create Date: 2026-05-20 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5a98653dd149'
down_revision: str | None = '1476b5e01b22'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'notification_config',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('feishu_webhook_url', sa.String(length=512), nullable=True),
        sa.Column('tg_bot_token', sa.String(length=128), nullable=True),
        sa.Column('tg_chat_id', sa.String(length=64), nullable=True),
        sa.Column(
            'trade_alert_enabled',
            sa.Boolean(), server_default=sa.text('true'), nullable=False,
        ),
        sa.Column(
            'price_alert_enabled',
            sa.Boolean(), server_default=sa.text('true'), nullable=False,
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('notification_config')
