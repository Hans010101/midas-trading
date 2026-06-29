"""user.is_platinum 铂金标记(多账户 PR-1 权限层)

铂金 = superadmin 手动设置的独立标记(非付费档 · 独立于 pro 订阅)· is_platinum=true → resolve_plan 返
'pro'(享受所有 pro 权益)· 后续 PR 解锁托管/智能/每日推文 3 功能 + 每用户独立账户。

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-06-29

★revision 选 l3m4n5o6p7q8(grep 确认 0 命中 · 避连续碰撞教训 docs/decisions/0010)。
★server_default false:存量用户默认非铂金 · 不破坏现有(同 demo_prefilled 范式)。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "l3m4n5o6p7q8"
down_revision = "k2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "is_platinum", sa.Boolean(), server_default=sa.text("false"), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "is_platinum")
