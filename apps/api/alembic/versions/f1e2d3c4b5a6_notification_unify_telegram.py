"""notification_config 统一 Telegram bot · 0025 G2a(不可逆 · 有损)

Revision ID: f1e2d3c4b5a6
Revises: a1c2e3f4d5b6
Create Date: 2026-05-27

==============================================================================
⚠️ 不可逆有损迁移 · 只动 notification_config 这一张表,绝不触碰其它表。
   (不动 user / virtual_account / virtual_order / virtual_perp_* /
    watchlist / 任何交易或用户数据。)

升级(upgrade)逐条:
  1) DROP COLUMN feishu_webhook_url
     · 为什么:0025 决策 D8 飞书通道完全移除,该列不再被任何代码读写。
     · 影响:存量飞书 webhook URL 永久丢失(产品方 D3 已确认接受有损迁移)。
  2) DROP COLUMN tg_bot_token
     · 为什么:统一 bot 模型下 bot token 移到全局 env(settings.tg_bot_token),
       不再 per-user 存储。
     · 影响:存量 per-user bot token 永久丢失(用户改用统一 bot,无需自己的 token)。
  3) UPDATE notification_config SET tg_chat_id = NULL(只清这一列)
     · 为什么:旧 tg_chat_id 对应的是用户各自的旧 bot,对统一 bot 失效
       (chat_id 是 (bot,chat) 对绑定的);保留会把消息发到错误/失效目标。
     · 影响:所有存量 Telegram 绑定清空,用户需经 /start 重新绑定
       (D3 已接受;G3 做显眼重绑提示)。此操作只改 tg_chat_id 一列,
       trade_alert_enabled / price_alert_enabled / 时间戳等其它列不动。
  4) CREATE partial UNIQUE INDEX uq_notification_config_tg_chat_id
     · 为什么:一 chat 一账号(防一个 Telegram 绑多个 Midas 账号 · 决策 D2)。
     · 形态:partial(WHERE tg_chat_id IS NOT NULL),允许多用户都未绑定(NULL)。
     · 影响:纯约束新增;在第 3 步清空后建,表内此时无非空 tg_chat_id,无冲突风险。

降级(downgrade):恢复 schema(列 + 去索引),但**数据不可恢复**:
  · 重新加回的 feishu_webhook_url / tg_bot_token 为空(原值已永久丢失)。
  · 已清空的 tg_chat_id 不会被还原(仍为 NULL)。
==============================================================================
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f1e2d3c4b5a6"
down_revision = "a1c2e3f4d5b6"
branch_labels = None
depends_on = None

_TABLE = "notification_config"
_TG_CHAT_INDEX = "uq_notification_config_tg_chat_id"


def upgrade() -> None:
    # 1) 移除飞书 webhook 列(飞书通道完全下线)
    op.drop_column(_TABLE, "feishu_webhook_url")

    # 2) 移除 per-user TG bot token 列(token 改走全局 env)
    op.drop_column(_TABLE, "tg_bot_token")

    # 3) 清空所有存量 tg_chat_id(旧 chat_id 对统一 bot 失效 · 强制全员重绑)
    #    只更新这一列;不触碰其它列、不触碰其它表。
    op.execute(sa.text(f"UPDATE {_TABLE} SET tg_chat_id = NULL"))  # noqa: S608

    # 4) tg_chat_id 加 partial 唯一索引(一 chat 一账号 · 仅约束非 NULL)
    op.create_index(
        _TG_CHAT_INDEX,
        _TABLE,
        ["tg_chat_id"],
        unique=True,
        postgresql_where=sa.text("tg_chat_id IS NOT NULL"),
    )


def downgrade() -> None:
    # 注:仅恢复 schema · 数据已永久丢失(见模块 docstring)。
    op.drop_index(_TG_CHAT_INDEX, table_name=_TABLE)
    op.add_column(
        _TABLE, sa.Column("tg_bot_token", sa.String(length=128), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("feishu_webhook_url", sa.String(length=512), nullable=True),
    )
