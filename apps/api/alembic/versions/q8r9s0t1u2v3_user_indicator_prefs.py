"""user.indicator_prefs 指标偏好(做T线后端)

前端读它决定展示哪些分析(布林/缠论默认 ON · 做T默认 OFF)。JSONB 可扩展、
nullable 不破存量(现有用户 NULL → 端点合并默认)。纯偏好存储 · 不碰引擎/影子/交易。

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
Create Date: 2026-07-05

★revision 选 q8r9s0t1u2v3(grep 确认 0 命中 · 避连续碰撞教训 docs/decisions/0010)。
★接单一 head p7q8r9s0t1u2(SEO 批6 · alembic heads 确认单 head)。
★nullable=True 无 server_default:现有用户该列 NULL · 端点侧合并默认(零感知)。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "q8r9s0t1u2v3"
down_revision = "p7q8r9s0t1u2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("indicator_prefs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user", "indicator_prefs")
