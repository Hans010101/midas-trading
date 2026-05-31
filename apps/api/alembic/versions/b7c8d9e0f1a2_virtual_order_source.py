"""virtual_order + virtual_perp_order 加 source 列 · ADR 0036 U0(AI 模拟交易下单来源标记 · 纯新增可逆)。

Revision ID: b7c8d9e0f1a2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-31

给两张订单流水表各加 1 个【非空 + server_default 'manual'】列:
- virtual_order.source       VARCHAR(16) NOT NULL DEFAULT 'manual'
- virtual_perp_order.source  VARCHAR(16) NOT NULL DEFAULT 'manual'
取值:manual(网页手动)/ bot(Telegram)/ ai_signal(AI 建议单)/ ai_strategy(AI 策略单)。

🔴 红线 / 零回归:
- 纯 ADD COLUMN · 不删不改任何现有列 / 索引 / 约束 · 撮合引擎与现有路由零改动。
- server_default 'manual' → 存量所有订单行 backfill 为 'manual'(老数据语义不变 · 老路径行为不变)。
- 来源标记是【元数据】· 不参与撮合 / 余额 / 保证金 / 强平任何计算 · 绝不接真实交易通道。
- downgrade 直接 DROP COLUMN(完全可逆)· 已演练 up → down → up。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1a2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

_TABLES = ("virtual_order", "virtual_perp_order")
_COL = "source"


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                _COL,
                sa.String(length=16),
                nullable=False,
                server_default="manual",
            ),
        )


def downgrade() -> None:
    # 纯新增 · 直接 drop · 无现有数据损失(source 是本期新增列)。
    for table in _TABLES:
        op.drop_column(table, _COL)
