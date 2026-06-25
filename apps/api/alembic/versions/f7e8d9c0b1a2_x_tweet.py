"""x_tweet 每日推文表(X 营销阶段4a · PR-1)· admin 生成的推文 + 门禁结果 + 截图 → 待发

24h 临时存储(清理 beat 删行+删截图文件)· 无唯一约束(一天可多条)· 状态止于 draft(待发)·
发布 posted/failed 留阶段4b。门禁不过的也存(compliance_passed=false + reason),4b 不可发。

Revision ID: f7e8d9c0b1a2
Revises: b2c3d4e5f6a7
Create Date: 2026-06-25 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7e8d9c0b1a2"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "x_tweet",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("bias", sa.String(length=8), nullable=False),
        sa.Column("tweet_text", sa.Text(), nullable=False),
        sa.Column("image_path", sa.String(length=512), nullable=True),
        sa.Column("compliance_passed", sa.Boolean(), nullable=False),
        sa.Column("compliance_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("generated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["generated_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # 列表查询 / 24h 清理都按 created_at 过滤 → 建索引
    op.create_index("ix_x_tweet_created_at", "x_tweet", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_x_tweet_created_at", table_name="x_tweet")
    op.drop_table("x_tweet")
