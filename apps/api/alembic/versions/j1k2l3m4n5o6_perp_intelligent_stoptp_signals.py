"""perp intelligent 止损/止盈价 + 共振明细(智能交易 PR-4 开仓编排)

Revision ID: j1k2l3m4n5o6
Revises: i1n2t3e4l5g6
Create Date: 2026-06-28

★3 列 nullable:止损/止盈价 Numeric(20,8)(PR-5 平仓判价)· 共振明细 JSONB(PR-6 看板/PR-7 复盘)·
引擎零碰 · 仿 managed 范式。★revision 选 j1k2l3m4n5o6(grep 确认 0 命中 · 避连续碰撞教训)。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "j1k2l3m4n5o6"
down_revision = "i1n2t3e4l5g6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "virtual_perp_position",
        sa.Column("intelligent_stop_price", sa.Numeric(20, 8), nullable=True),
    )
    op.add_column(
        "virtual_perp_position",
        sa.Column("intelligent_tp_price", sa.Numeric(20, 8), nullable=True),
    )
    op.add_column(
        "virtual_perp_position",
        sa.Column("intelligent_signals", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("virtual_perp_position", "intelligent_signals")
    op.drop_column("virtual_perp_position", "intelligent_tp_price")
    op.drop_column("virtual_perp_position", "intelligent_stop_price")
