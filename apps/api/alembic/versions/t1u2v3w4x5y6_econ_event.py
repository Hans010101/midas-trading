"""建 econ_event 表(事件日程提醒层 P0 · 前瞻宏观日历)。

PG 而非 CH(调研 §5.2):事件是可变实体(改期 UPDATE·event_key 幂等 upsert),
年增 ~150 行。只存日程不存实际值。

Revision ID: t1u2v3w4x5y6
Revises: s0t1u2v3w4x5
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "t1u2v3w4x5y6"
down_revision = "s0t1u2v3w4x5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "econ_event",
        sa.Column("event_key", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("markets", JSONB(), nullable=False),
        sa.Column("importance", sa.SmallInteger(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_confirmed", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_econ_event_event_type", "econ_event", ["event_type"])
    op.create_index("ix_econ_event_scheduled_at", "econ_event", ["scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_econ_event_scheduled_at", table_name="econ_event")
    op.drop_index("ix_econ_event_event_type", table_name="econ_event")
    op.drop_table("econ_event")
