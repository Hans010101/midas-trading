"""conditional_perp_limit_fields

条件单二期刀1:conditional_orders 加 perp 限价开仓字段(leverage/margin/margin_mode/
expires_at)· 全 nullable(仅 perp LIMIT 用 · spot/SLTP 留 NULL)。
⛔ 仅落字段 + 端点放开挂单;触发→开仓(route_open_perp)留刀2。

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-13 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: str | None = 'c1d2e3f4a5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('conditional_orders', sa.Column('leverage', sa.Integer(), nullable=True))
    op.add_column('conditional_orders', sa.Column('margin', sa.Numeric(20, 8), nullable=True))
    op.add_column('conditional_orders', sa.Column('margin_mode', sa.String(length=16), nullable=True))
    op.add_column(
        'conditional_orders',
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conditional_orders', 'expires_at')
    op.drop_column('conditional_orders', 'margin_mode')
    op.drop_column('conditional_orders', 'margin')
    op.drop_column('conditional_orders', 'leverage')
