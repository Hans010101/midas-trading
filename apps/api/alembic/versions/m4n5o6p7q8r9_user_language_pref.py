"""user.language_pref 语言偏好(i18n Phase 0)

i18n 第一批地基:用户语言偏好字段(中/英)· 双层存储的后端层——
cookie 即时生效(前端复用涨跌色范式)+ 此字段登录后跨设备同步。

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-07-01

★revision 选 m4n5o6p7q8r9(grep 确认 0 命中 · 避连续碰撞教训 docs/decisions/0010)。
★nullable 无 server_default:NULL = 跟随浏览器/cookie · 不强制存量用户为某语言(前端 cookie 兜底)·
  不破坏现有(同 avatar_id nullable 范式)。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "m4n5o6p7q8r9"
down_revision = "l3m4n5o6p7q8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("language_pref", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user", "language_pref")
