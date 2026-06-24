"""notification_config 做T通知拆两体系(做T M2-4)· 加 dott_digest_enabled + dott_transition_enabled

把 M2-2 的单个 dott_alert_enabled 拆成两个对应两推送体系:
- dott_digest_enabled(体系1 · 每小时定时全景 M2-3a)
- dott_transition_enabled(体系2 · 行情转换 M2-3b)
都 bool · 默认 false(Pro 专属 opt-in)。旧 dott_alert_enabled 列【保留但废弃】(不再读写)·
默认 false + Pro 门控 + 仅上线 1 天 → 采用率≈0,新字段都默认 false,不回填。

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-24 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_config",
        sa.Column(
            "dott_digest_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "notification_config",
        sa.Column(
            "dott_transition_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_config", "dott_transition_enabled")
    op.drop_column("notification_config", "dott_digest_enabled")
