"""virtual_perp_position 加 managed_close_reason 字段(托管交易 PR-3 · 平仓原因)

★nullable(无 server_default):只托管单平仓才写(tp/signal/timeout)· 普通单 / 持仓中 / 非托管都是 NULL。
引擎枚举 PerpCloseReason 零碰(托管平仓原因记自己的 nullable 列)· PR-4 前向测试统计按原因分类。

★revision id 用 c4d5e6f7a8b9(a1b2c3d4e5f6 已被 notification_dott_alert 占,避撞)。

Revision ID: c4d5e6f7a8b9
Revises: f0a1b2c3d4e5
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "virtual_perp_position",
        sa.Column("managed_close_reason", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("virtual_perp_position", "managed_close_reason")
