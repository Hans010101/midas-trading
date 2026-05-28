"""virtual_perp_position.margin_mode · PG Enum → VARCHAR(16)(ADR-0027 MC-1 · DP-5)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-28

═══════════════════════════════════════════════════════════════════════════
MC-1(全仓地基)· 只把保证金模式字段从 PG Enum 改成 VARCHAR(16),为后续全仓
'cross' 值扩容,免去 `ALTER TYPE ... ADD VALUE`(不可逆、且历史上需锁表)的坑。
本期【不】实现任何全仓逻辑 —— 现网所有行只可能是逐仓,迁移后值统一归一为
小写 'isolated'(与 StrEnum MarginMode.ISOLATED.value 一致,供 worker 过滤 `==` 命中)。

🔴 关键归一:原 Enum 存的是 .name = 'ISOLATED'(大写);
   改 String 后引擎写入 MarginMode.ISOLATED → 存 .value = 'isolated'(小写)。
   若不归一,老行 'ISOLATED' 会与新行 'isolated' 不一致,worker 过滤
   `margin_mode == 'isolated'` 漏扫老逐仓仓位 → 该平的不平(严重)。
   故 upgrade 用 `USING lower(margin_mode::text)` 把存量大写一次性压成小写。

可逆性:
- upgrade / downgrade 均为显式分步 SQL,完全可逆。
- ⚠️ downgrade 前提:表内无 'cross' 行(MC-1 阶段恒成立 —— 全仓代码尚未落地)。
  若 MC-2+ 之后已产生 'cross' 持仓,则不可直接 downgrade(upper('cross')='CROSS'
  不在 enum('ISOLATED') 内,cast 会失败)—— 届时需先转/清 cross 行再回滚。
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 先摘掉 enum 默认值(否则改列类型时默认表达式会卡住)
    op.execute(
        "ALTER TABLE virtual_perp_position ALTER COLUMN margin_mode DROP DEFAULT",
    )
    # 2) 改列类型 Enum → VARCHAR(16),同时把存量 'ISOLATED' 归一成小写 'isolated'
    op.execute(
        "ALTER TABLE virtual_perp_position "
        "ALTER COLUMN margin_mode TYPE VARCHAR(16) "
        "USING lower(margin_mode::text)",
    )
    # 3) 重新挂上小写默认值(与模型 server_default text('isolated') 对齐)
    op.execute(
        "ALTER TABLE virtual_perp_position "
        "ALTER COLUMN margin_mode SET DEFAULT 'isolated'",
    )
    # 4) PG enum 类型已无任何列引用(仅本列用过)· 干净删除
    op.execute("DROP TYPE margin_mode")


def downgrade() -> None:
    # 1) 重建原 PG enum(原始定义只有大写 'ISOLATED' 一个值)
    op.execute("CREATE TYPE margin_mode AS ENUM ('ISOLATED')")
    # 2) 摘掉小写默认值
    op.execute(
        "ALTER TABLE virtual_perp_position ALTER COLUMN margin_mode DROP DEFAULT",
    )
    # 3) VARCHAR → Enum · 用 upper() 还原大写(假设无 'cross' 行 · 见文件头)
    op.execute(
        "ALTER TABLE virtual_perp_position "
        "ALTER COLUMN margin_mode TYPE margin_mode "
        "USING upper(margin_mode)::margin_mode",
    )
    # 4) 还原原始大写默认值
    op.execute(
        "ALTER TABLE virtual_perp_position "
        "ALTER COLUMN margin_mode SET DEFAULT 'ISOLATED'",
    )
