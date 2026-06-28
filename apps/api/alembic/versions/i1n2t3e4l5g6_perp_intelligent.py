"""perp intelligent 标记 + intelligent_close_reason(智能交易 PR-2 地基)

Revision ID: i1n2t3e4l5g6
Revises: f0e1d2c3b4a5
Create Date: 2026-06-28

★server_default=false 兼容老数据 · close_reason nullable · 仿 managed 范式 · 引擎零碰。
★revision 选 i1n2t3e4l5g6(grep 确认 0 命中 · 避连续碰撞教训)。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "i1n2t3e4l5g6"
down_revision = "f0e1d2c3b4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "virtual_perp_position",
        sa.Column(
            "intelligent", sa.Boolean(), server_default=sa.text("false"), nullable=False,
        ),
    )
    op.add_column(
        "virtual_perp_position",
        sa.Column("intelligent_close_reason", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("virtual_perp_position", "intelligent_close_reason")
    op.drop_column("virtual_perp_position", "intelligent")
