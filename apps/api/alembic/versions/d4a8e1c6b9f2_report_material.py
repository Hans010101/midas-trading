"""report_material · 周报素材(第三刀-A)

纯增量新表(report_material · admin 上传 md/PDF 素材提取文本 + OSS 键 + 周期标记)·
不改任何现有表。OSS 上传第三刀-B 接;本迁移只建表。

Revision ID: d4a8e1c6b9f2
Revises: c2e5f8a1b4d7
Create Date: 2026-06-21 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a8e1c6b9f2"
down_revision: str | None = "c2e5f8a1b4d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_material",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("oss_key", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_report_material_created", "report_material", ["created_at"], unique=False,
    )
    op.create_index(
        "ix_report_material_period",
        "report_material",
        ["period_start", "period_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_report_material_period", table_name="report_material")
    op.drop_index("ix_report_material_created", table_name="report_material")
    op.drop_table("report_material")
