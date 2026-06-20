"""notification_config.weekly_report_enabled · 市场周报订阅开关(P3/P4 第二刀)

加一列 weekly_report_enabled(bool · 默认 false = 选择性订阅 opt-in)。不改任何现有列。

Revision ID: c2e5f8a1b4d7
Revises: b7d3f1a9c2e5
Create Date: 2026-06-20 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2e5f8a1b4d7"
down_revision: str | None = "b7d3f1a9c2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_config",
        sa.Column(
            "weekly_report_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_config", "weekly_report_enabled")
