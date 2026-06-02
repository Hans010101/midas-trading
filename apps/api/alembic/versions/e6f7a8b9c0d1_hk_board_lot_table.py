"""hk_board_lot 表 · 港股下单池扩量 A2(HKEX 官方 board lot · 纯新增表 · 可逆)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-02

═══════════════════════════════════════════════════════════════════════════
港股下单池从 18 硬编码种子扩到 ~2406 主板 HKD(每手股数全用港交所官方)。
worker `tasks.market.hk_board_lot_scan` 每日采 HKEX ListOfSecurities → upsert 本表。
get_hk_board_lot(db, code) 优先读本表 · 表无回退 18 种子(过渡/兜底)。

★ 纯新增表 · 无既有数据 · 无列类型变更(区别于 d5e6f7a8b9c0 改列)→ 低风险、完全可逆。
🔴 只读引用数据 · 下单按手取整用 · 不参与撮合/余额。
═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hk_board_lot",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("lot", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code"),
    )


def downgrade() -> None:
    op.drop_table("hk_board_lot")
