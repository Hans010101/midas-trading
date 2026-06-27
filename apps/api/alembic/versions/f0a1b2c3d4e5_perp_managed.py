"""virtual_perp_position 加 managed 字段(托管交易 PR-1 · 策略前向测试)

★server_default='false':老数据 + 非原子部署旧代码读到的行都默认 False(非托管),不崩
(项目铁律:加非空字段必带 server_default 回填)。

managed=True:托管交易(独立系统账户)开的单 · 用途:① 统计/展示 ② 强平 worker 跳过(禁强平,
只对托管单生效,引擎纯函数零改)。

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "virtual_perp_position",
        sa.Column(
            "managed", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("virtual_perp_position", "managed")
