"""x_tweet 加 auto_drafted 字段(X 营销自动托管频率调整 · 标记自动起草素材)

★server_default='false':老数据 + 非原子部署旧代码读到的行都默认 False(手动),不崩
(项目铁律:加非空字段必带 server_default 回填)。

auto_drafted=True:自动托管起草的推文(每轮 2 条均标)· 用途:① 后台「待补发素材」识别
② 人工补发计入 30 日配额(配额"算":自动发 + 人工补发共用 x:auto:daily_count)。

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "x_tweet",
        sa.Column(
            "auto_drafted", sa.Boolean(),
            server_default="false", nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("x_tweet", "auto_drafted")
