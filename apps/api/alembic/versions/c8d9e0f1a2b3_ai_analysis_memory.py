"""ai_analysis_memory 表 · ADR 0036 批次乙(AI 决策卡历史记录 · 自学习闭环地基)。

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-31

═══════════════════════════════════════════════════════════════════════════
🔴 红线 / 零回归:
- 纯【新建表】+【新建索引】· 不动任何现有表 / 列 / 索引 / 约束。
- 不接入撮合 / 不改 analyze 主流程 · 仅供端点旁路记录 + reflection 回填 + 命中率统计。
- 表数据是纯只读元数据 · 失败必须吞掉 · 永不阻塞决策卡响应。
- downgrade 直接 DROP TABLE(纯新增 · 完全可逆)· 已演练 up → down → up。
═══════════════════════════════════════════════════════════════════════════

字段说明见 app/models/ai_analysis_memory.py。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


_TABLE = "ai_analysis_memory"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column(
            "instrument",
            sa.String(length=8),
            nullable=False,
            server_default="spot",
        ),
        sa.Column("period", sa.String(length=8), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("composite_score", sa.Integer(), nullable=False),
        sa.Column("composite_label", sa.String(length=8), nullable=False),
        sa.Column("composite_confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("price_at", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("llm_mode", sa.String(length=8), nullable=False),
        # Reflection 回填列(初写全 NULL)
        sa.Column("reflected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_after", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("actual_return", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("was_correct", sa.Boolean(), nullable=True),
    )

    # 索引设计见 app/models/ai_analysis_memory.py(__table_args__ 注释)。
    op.create_index(
        "ix_ai_memory_analyzed_at",
        _TABLE,
        ["analyzed_at"],
    )
    op.create_index(
        "ix_ai_memory_pending_reflection",
        _TABLE,
        ["analyzed_at"],
        postgresql_where=sa.text("reflected_at IS NULL"),
    )
    op.create_index(
        "ix_ai_memory_market_reflected",
        _TABLE,
        ["market", "reflected_at"],
    )


def downgrade() -> None:
    # 纯新建 · 直接 drop · 无现有数据(本期新增表)
    op.drop_index("ix_ai_memory_market_reflected", table_name=_TABLE)
    op.drop_index("ix_ai_memory_pending_reflection", table_name=_TABLE)
    op.drop_index("ix_ai_memory_analyzed_at", table_name=_TABLE)
    op.drop_table(_TABLE)
