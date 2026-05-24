"""perp_funding_settlement

ADR-0020 E5 · M2-C.2.2 · 资金费结算流水表 virtual_perp_funding。

每条 = 某活仓在某结算整点被收 / 付的一次资金费(可复盘)。
结算服务只扣虚拟现金 + 累加 position.funding_paid + 写本表(E4=A · 不联动强平)。

复用:
- FK → virtual_account.id + virtual_perp_position.id(均 CASCADE)
- perp_side enum(M2-C.1 c9f1e2d3b4a5 已建 · create_type=False 引用,不重建)

幂等:(position_id, funding_ts) 唯一 · 同结算点重跑不重复扣费。

🔴 红线:只建 schema · 全程虚拟资金,绝不接真实资金费 / 转账。

Revision ID: b3d7f1a9e2c4
Revises: c9f1e2d3b4a5
Create Date: 2026-05-24 11:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d7f1a9e2c4"
down_revision: str | None = "c9f1e2d3b4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "virtual_perp_funding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        # 复用 M2-C.1 已建的 perp_side 类型 · 不重建(create_type=False)
        sa.Column(
            "side",
            postgresql.ENUM("LONG", "SHORT", name="perp_side", create_type=False),
            nullable=False,
        ),
        sa.Column("funding_rate", sa.Numeric(20, 8), nullable=False),
        sa.Column("mark_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("payment", sa.Numeric(20, 4), nullable=False),
        sa.Column("funding_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "settled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["virtual_account.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["position_id"], ["virtual_perp_position.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # 幂等 · 同一活仓同一结算整点只结算一次
    op.create_index(
        "uq_perp_funding_position_ts",
        "virtual_perp_funding",
        ["position_id", "funding_ts"],
        unique=True,
    )
    op.create_index(
        "ix_perp_funding_account_settled",
        "virtual_perp_funding",
        ["account_id", "settled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_perp_funding_account_settled", table_name="virtual_perp_funding",
    )
    op.drop_index(
        "uq_perp_funding_position_ts", table_name="virtual_perp_funding",
    )
    op.drop_table("virtual_perp_funding")
    # perp_side enum 是 M2-C.1 建的,本 migration 复用未建 · 不 drop
