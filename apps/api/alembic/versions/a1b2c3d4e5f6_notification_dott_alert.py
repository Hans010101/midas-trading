"""notification_config.dott_alert_enabled · 做T信号 TG 通知订阅开关(做T M2-2)

加一列 dott_alert_enabled(bool · 默认 false = Pro 专属 opt-in 订阅)。不改任何现有列。
★本刀(M2-2)只建订阅开关,不真发 TG(真发 M2-3 接 boll_scan 广播 · 影子门仍在)。

Revision ID: a1b2c3d4e5f6
Revises: e7f2a4c8d1b6
Create Date: 2026-06-24 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "e7f2a4c8d1b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_config",
        sa.Column(
            "dott_alert_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_config", "dott_alert_enabled")
