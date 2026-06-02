"""virtual_account.currency · PG Enum → VARCHAR(8)(照 d4e5f6a7b8c9 先例 · 为 HKD 等币种扩容)

Revision ID: d5e6f7a8b9c0
Revises: c8d9e0f1a2b3
Create Date: 2026-06-02

═══════════════════════════════════════════════════════════════════════════
根因:currency PG enum 建表时(1476b5e01b22)只有 'CNY','USD','USDT' · 无 'HKD' ·
  Python Currency enum 后加了 HKD 但 DB enum 没跟着迁移 → 激活港股账户(写
  currency='HKD')被 PG 拒(invalid input value for enum currency: "HKD")·
  只 hk 失败,cn/us/crypto(CNY/USD/USDT 在 enum 内)正常。

解法(照搬 margin_mode 同款 · ADR-0027 MC-1 先例 d4e5f6a7b8c9):
  currency 列 PG Enum → VARCHAR(8),免去 `ALTER TYPE ... ADD VALUE`(不可逆 + 需锁表)·
  与 market 列(本就是 String)对齐 · 未来加币种零迁移。

★ 现有数据保全:Currency StrEnum 的 .name == .value(CNY/USD/USDT 全大写)· 存量值
  `USING currency::text` 原样保留(不做大小写归一,区别于 margin_mode 的 lower())。
  currency 列无 server_default → 不需 DROP DEFAULT 步。

可逆性:
- downgrade 重建原 3 值 enum + 列转回。
- ⚠️ downgrade 前提:表内无 'HKD'(及其他非 CNY/USD/USDT)行 —— 若已有港股账户,
  'HKD'::currency 不在重建的 3 值 enum 内会 cast 失败 → 需先转/清 HKD 行再回滚。
═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) currency 列 Enum → VARCHAR(8)· 存量 CNY/USD/USDT 原样保留(无需归一)
    op.execute(
        "ALTER TABLE virtual_account "
        "ALTER COLUMN currency TYPE VARCHAR(8) "
        "USING currency::text",
    )
    # 2) currency PG enum 类型已无任何列引用(仅 virtual_account.currency 用过)· 干净删除
    op.execute("DROP TYPE currency")


def downgrade() -> None:
    # 1) 重建原 PG enum(原始 3 值)· ⚠️ 前提:表内无 HKD 等非原始值行(见文件头)
    op.execute("CREATE TYPE currency AS ENUM ('CNY', 'USD', 'USDT')")
    # 2) VARCHAR → Enum(存量值原样 cast 回 · 无需大小写处理)
    op.execute(
        "ALTER TABLE virtual_account "
        "ALTER COLUMN currency TYPE currency "
        "USING currency::currency",
    )
