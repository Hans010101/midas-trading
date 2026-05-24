"""virtual position_side(卖空 · 0023 阶段③ · 3.4 批1)

给 virtual_position / virtual_order 加 position_side(LONG/SHORT)· 存量行 backfill=LONG。
卖空作为 LONG 之外的新增方向 · 现货做多(LONG)路径零改动。

Revision ID: a1c2e3f4d5b6
Revises: b3d7f1a9e2c4
Create Date: 2026-05-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1c2e3f4d5b6"
down_revision: str | None = "b3d7f1a9e2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLAlchemy Enum 默认按成员 .name 存(跟 order_side/order_status 一致)→ 值为 'LONG'/'SHORT'。
# create_type=False:类型由下面的显式 .create() 建一次,两个 add_column 不再各自重建
# (否则第二个 add_column 会 DuplicateObject · 见 perp 迁移复用 order_status 同款手法)。
_POSITION_SIDE = postgresql.ENUM(
    "LONG", "SHORT", name="position_side", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    # 显式建类型一次(checkfirst 容忍重跑)· add_column 用 create_type=False 不再重建
    _POSITION_SIDE.create(bind, checkfirst=True)
    # NOT NULL + server_default 'LONG' · 一次性把存量行(全是做多)backfill 为 LONG
    op.add_column(
        "virtual_position",
        sa.Column(
            "position_side", _POSITION_SIDE, nullable=False, server_default="LONG",
        ),
    )
    op.add_column(
        "virtual_order",
        sa.Column(
            "position_side", _POSITION_SIDE, nullable=False, server_default="LONG",
        ),
    )


def downgrade() -> None:
    op.drop_column("virtual_order", "position_side")
    op.drop_column("virtual_position", "position_side")
    sa.Enum(name="position_side").drop(op.get_bind(), checkfirst=False)
