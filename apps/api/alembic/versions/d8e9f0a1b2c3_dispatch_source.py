"""platform_dispatch 加 source 字段(X 营销自动托管 PR-1 · auto/manual)

★server_default='manual':老数据 + 非原子部署旧代码读到的行都默认 manual,不崩(项目铁律:
加非空字段必带 server_default 回填,避免跨版本 ValidationError 500)。

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_dispatch",
        sa.Column(
            "source", sa.String(length=16),
            server_default="manual", nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("platform_dispatch", "source")
