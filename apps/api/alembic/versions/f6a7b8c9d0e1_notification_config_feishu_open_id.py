"""notification_config 加 feishu_open_id · ADR 0032 阶段二飞书通知(纯新增可逆)。

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-29

加 1 个【可空】列 + 1 个 partial 唯一索引:
- feishu_open_id VARCHAR(64) NULL(飞书绑定后写入 · 阶段三 bind-token;未绑定为 NULL)
- uq_notification_config_feishu_open_id:feishu_open_id 非空时唯一(一飞书用户一账号),
  partial(WHERE feishu_open_id IS NOT NULL)· 与 tg_chat_id 的 partial 唯一索引同模式。

🔴 红线 / 零回归:
- 可空列 · 无 server_default · 现有行该列为 NULL(老用户无任何行为变化)。
- 不删不改任何现有列 · pure ADD COLUMN + ADD INDEX · downgrade 直接 DROP(完全可逆)。
- 不碰其他表;tg_chat_id / quiet_hours_* 等现有列与索引均不动。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

_TABLE = "notification_config"
_INDEX = "uq_notification_config_feishu_open_id"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("feishu_open_id", sa.String(length=64), nullable=True),
    )
    # 一飞书用户一账号 · partial 唯一(只约束非 NULL)· 允许多用户都未绑定。
    op.create_index(
        _INDEX,
        _TABLE,
        ["feishu_open_id"],
        unique=True,
        postgresql_where=sa.text("feishu_open_id IS NOT NULL"),
    )


def downgrade() -> None:
    # 纯新增 · 直接 drop · 无现有数据损失(feishu_open_id 是本期新增列)。
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "feishu_open_id")
