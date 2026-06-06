"""backtest_runs 表 · 研究室回测结果落库(P1-4c 块3 · 纯新增表 · 可逆)

Revision ID: b1c2d3e4f5a6
Revises: f7a8b9c0d1e2
Create Date: 2026-06-05

═══════════════════════════════════════════════════════════════════════════
研究室回测(vibe 路径B)运行记录:入参 + 状态机(pending→done/error)+ 16 指标(JSONB)。
api/Celery 触发 → midas-vibe 容器执行 → 解析 artifacts 回填。

★ 纯新增表 · 无既有数据 · 无列类型变更 → 低风险、完全可逆。
🔴 只读研究记录 · 绝不参与下单 / 撮合 / 余额。user_id 软引用(无 FK 约束)。
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("period", sa.String(length=8), nullable=False),
        sa.Column("start_date", sa.String(length=16), nullable=False),
        sa.Column("end_date", sa.String(length=16), nullable=False),
        sa.Column("params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_runs_user_created",
        "backtest_runs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_user_created", table_name="backtest_runs")
    op.drop_table("backtest_runs")
