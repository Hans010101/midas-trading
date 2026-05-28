"""notification_config 加 quiet_hours_* · 0028 N1 安静时段(纯新增可逆)。

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-28

加 4 个 NOT NULL + server_default 字段:
- quiet_hours_enabled BOOLEAN DEFAULT true(DP4 默认开启)
- quiet_hours_start SMALLINT DEFAULT 23(每日 23 点开始)
- quiet_hours_end SMALLINT DEFAULT 7(次日 7 点结束 · 跨夜)
- quiet_hours_tz VARCHAR(64) DEFAULT 'Asia/Shanghai'(DP5 主力东八)

🔴 红线 / 零回归:
- 现有行立即有合理默认(老用户行为变成"夜间静默"· 这是 DP4 拍板)
- 不删不改任何现有列 · pure ADD COLUMN · downgrade 直接 DROP 4 列(可逆)
- 不碰其他表
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

_TABLE = "notification_config"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "quiet_hours_enabled", sa.Boolean(),
            nullable=False, server_default=sa.text("true"),
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "quiet_hours_start", sa.SmallInteger(),
            nullable=False, server_default=sa.text("23"),
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "quiet_hours_end", sa.SmallInteger(),
            nullable=False, server_default=sa.text("7"),
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "quiet_hours_tz", sa.String(length=64),
            nullable=False, server_default=sa.text("'Asia/Shanghai'"),
        ),
    )


def downgrade() -> None:
    # 纯新增列 · 直接 drop · 无现有数据损失(quiet_hours_* 是本期新增)
    op.drop_column(_TABLE, "quiet_hours_tz")
    op.drop_column(_TABLE, "quiet_hours_end")
    op.drop_column(_TABLE, "quiet_hours_start")
    op.drop_column(_TABLE, "quiet_hours_enabled")
