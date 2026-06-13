"""ai_usage_user_id

会员 Phase 1 刀1(⑤ 审计债):ai_usage_log 加 user_id(调研 P1 确认的缺口)。
nullable —— 存量行 + 匿名决策卡(decision-card 匿名可调)天然 NULL。

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-13 10:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c6d7e8f9a0b1'
down_revision: str | None = 'b5c6d7e8f9a0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('ai_usage_log', sa.Column('user_id', sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column('ai_usage_log', 'user_id')
