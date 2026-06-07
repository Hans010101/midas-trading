"""backtest_runs add equity/trades/run_card json · P1-4c.5 full-data(纯增量列 · 可逆)

Revision ID: f2a3b4c5d6e7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-07

═══════════════════════════════════════════════════════════════════════════
P1-4c.5(ADR 0038 D4 · B 档报告 UI):原 backtest_runs 只落 metrics_json(16 指标),
equity 曲线 / 逐笔 trades / run_card 方法学脚注被 persist 丢弃 → 前端取不到。
本迁移加 3 个 JSONB nullable 列(与 metrics_json 同款:done 时才回填),persist_result 扩写后落库。

★ 纯新增列 · 无既有数据依赖 · nullable 无 server_default → 低风险、完全可逆。
🔴 只读研究记录 · 绝不参与下单 / 撮合 / 余额。
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "f2a3b4c5d6e7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backtest_runs",
        sa.Column("equity_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "backtest_runs",
        sa.Column("trades_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "backtest_runs",
        sa.Column("run_card_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backtest_runs", "run_card_json")
    op.drop_column("backtest_runs", "trades_json")
    op.drop_column("backtest_runs", "equity_json")
