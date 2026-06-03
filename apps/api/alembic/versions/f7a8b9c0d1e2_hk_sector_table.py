"""hk_sector 表 · 港股板块 A2(yfinance GICS 行业源 · 纯新增表 · 可逆)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-03

═══════════════════════════════════════════════════════════════════════════
港股首页板块区(对标 A股 CnSections)· 行业分类来自 yfinance `.info` 的 GICS sector。
worker `tasks.market.hk_sector_scan` 周级采行情池 ~900 只 → upsert 本表(code→sector 英文)。
`/hk/sectors` 端点 join 本表 + 新浪 spot → 按板块聚合(涨跌/家数/成交额)· sector 英→中映射在 service。

★ 纯新增表 · 无既有数据 · 无列类型变更 → 低风险、完全可逆。
🔴 只读行业分类数据 · 仅首页板块展示 · 不参与下单/撮合/余额。
═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hk_sector",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("sector", sa.String(length=48), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code"),
    )


def downgrade() -> None:
    op.drop_table("hk_sector")
