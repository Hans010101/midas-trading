"""SEO 批6 度量闭环:来源桶 / 来源域名 / AI 爬虫 三张按天聚合表

流量来源归因(D8 口径:域名 + utm 聚合桶 · 绝不 IP/UA/个体明细)+ AI 爬虫计数
(GEO 领先指标)。三表均 (date, dim) 复合唯一 · beat flush upsert 覆盖语义。

Revision ID: p7q8r9s0t1u2
Revises: n5o6p7q8r9s0
Create Date: 2026-07-04

★revision 选 p7q8r9s0t1u2(grep 确认 0 命中 · 避连续碰撞教训 docs/decisions/0010)。
★接单一 head n5o6p7q8r9s0(alembic heads 确认单 head · 非两 head 假象)。
★纯新增三表 · 不碰任何现有表 · 现有 daily_visit_stat(PV/UV)完全独立不动。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "p7q8r9s0t1u2"
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None


def _ts_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "daily_source_stat",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("pv", sa.BigInteger(), server_default="0", nullable=False),
        *_ts_cols(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "source", name="uq_source_date_source"),
    )
    op.create_index(op.f("ix_daily_source_stat_date"), "daily_source_stat", ["date"])

    op.create_table(
        "daily_referrer_stat",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("referrer", sa.String(length=120), nullable=False),
        sa.Column("pv", sa.BigInteger(), server_default="0", nullable=False),
        *_ts_cols(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "referrer", name="uq_referrer_date_referrer"),
    )
    op.create_index(op.f("ix_daily_referrer_stat_date"), "daily_referrer_stat", ["date"])

    op.create_table(
        "daily_crawler_stat",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("bot", sa.String(length=120), nullable=False),
        sa.Column("hits", sa.BigInteger(), server_default="0", nullable=False),
        *_ts_cols(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "bot", name="uq_crawler_date_bot"),
    )
    op.create_index(op.f("ix_daily_crawler_stat_date"), "daily_crawler_stat", ["date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_daily_crawler_stat_date"), table_name="daily_crawler_stat")
    op.drop_table("daily_crawler_stat")
    op.drop_index(op.f("ix_daily_referrer_stat_date"), table_name="daily_referrer_stat")
    op.drop_table("daily_referrer_stat")
    op.drop_index(op.f("ix_daily_source_stat_date"), table_name="daily_source_stat")
    op.drop_table("daily_source_stat")
