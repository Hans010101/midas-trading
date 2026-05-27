"""alert_rule 表 · 0025 G2b 告警规则引擎(纯新增 · 不碰任何现有表)

Revision ID: a7b8c9d0e1f2
Revises: f1e2d3c4b5a6
Create Date: 2026-05-27

纯新增一张 alert_rule 表 + 两个辅助索引。不修改 / 不删除任何现有表或列。
downgrade 直接 drop 该表(纯新增,可干净回滚,无数据损失风险)。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f1e2d3c4b5a6"
branch_labels = None
depends_on = None

_TABLE = "alert_rule"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("indicator", sa.String(length=48), nullable=False),
        sa.Column("operator", sa.String(length=8), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False,
        ),
        sa.Column(
            "cooldown_sec", sa.Integer(),
            server_default=sa.text("300"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rule_user_id", _TABLE, ["user_id"])
    op.create_index("ix_alert_rule_enabled", _TABLE, ["enabled"])


def downgrade() -> None:
    # 纯新增表 · 直接 drop(索引随表删除)· 无现有数据受影响。
    op.drop_index("ix_alert_rule_enabled", table_name=_TABLE)
    op.drop_index("ix_alert_rule_user_id", table_name=_TABLE)
    op.drop_table(_TABLE)
