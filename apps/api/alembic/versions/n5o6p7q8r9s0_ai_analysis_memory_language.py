"""ai_analysis_memory.language 生成语言(i18n Phase4 刀2)

en 决策卡地基:决策卡历史行记录【实际生成语言】(zh/en · 非用户偏好)。
同一用户切语言时,历史反映当时生成语言;命中率统计可按语言拆桶。

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-07-03

★revision 选 n5o6p7q8r9s0(grep 确认 0 命中 · 避连续碰撞教训 docs/decisions/0010)。
★接单一 head m4n5o6p7q8r9(60 迁移·宽松正则确认单 head·非两 head 假象)。
★nullable=False + server_default='zh':历史行 + 现有 zh 用户零感知(向后兼容)·
  同 ai_analysis_memory.instrument 的 server_default 范式。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "n5o6p7q8r9s0"
down_revision = "m4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_analysis_memory",
        sa.Column(
            "language",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'zh'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_analysis_memory", "language")
