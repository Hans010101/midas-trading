"""清理 select_kline ASC/DESC bug 修复前的脏虚拟交易数据 · 0010 配套。

背景:
  select_kline 之前用 `ORDER BY ts ASC LIMIT N` · 取最早 N 根 K 线 ·
  撮合 / 30s 报价 / 浮盈估值整条链路全错。在那个 bug 修复(2026-05-20)
  之前下的虚拟单,成交价是 2018 年的远古 K,持仓 / 盈亏 / 权益曲线全脏。

清理范围(产品负责人 2026-05-20 指令):
  - DELETE virtual_position  · 全部活/历史持仓
  - DELETE virtual_order     · 全部订单流水
  - DELETE virtual_equity_snapshot · 全部权益曲线点
  - UPDATE virtual_account SET cash_balance = initial_capital, realized_pnl = 0
    · 保留账户激活状态(不动 schema,不删 account row),只重置余额

不动:
  - virtual_account 本身(用户激活的市场设置保留)
  - users / watchlist_item / notification_config 等其他表

跑法:
  cd apps/api && .venv/bin/python scripts/cleanup_virtual_dirty_data.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 让脚本能 import app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "cleanup-only")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://midas:midas_dev@localhost:5432/midas",
)

from sqlalchemy import delete, func, select, update  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.models.virtual import (  # noqa: E402
    VirtualAccount,
    VirtualEquitySnapshot,
    VirtualOrder,
    VirtualPosition,
)


async def main() -> None:
    async with async_session_factory() as s:
        # 1. 清点旧数据
        before: dict[str, int] = {}
        for model, label in [
            (VirtualAccount, "accounts"),
            (VirtualPosition, "positions"),
            (VirtualOrder, "orders"),
            (VirtualEquitySnapshot, "equity_snapshots"),
        ]:
            count = (
                await s.execute(select(func.count()).select_from(model))
            ).scalar() or 0
            before[label] = count

        print("== 清理前 ==")
        for k, v in before.items():
            print(f"  {k}: {v}")

        # 2. 删除子表(positions / orders / equity_snapshots)
        # 顺序无所谓:都是 FK ondelete=CASCADE 到 virtual_account,
        # 但我们不删 account,所以三张子表互相独立,顺序自由
        for model in (VirtualPosition, VirtualOrder, VirtualEquitySnapshot):
            await s.execute(delete(model))

        # 3. 重置 account 的现金余额回 initial_capital,清零 realized_pnl
        await s.execute(
            update(VirtualAccount).values(
                cash_balance=VirtualAccount.initial_capital,
                realized_pnl=0,
            ),
        )

        await s.commit()

        # 4. 验证
        after: dict[str, int] = {}
        for model, label in [
            (VirtualAccount, "accounts"),
            (VirtualPosition, "positions"),
            (VirtualOrder, "orders"),
            (VirtualEquitySnapshot, "equity_snapshots"),
        ]:
            count = (
                await s.execute(select(func.count()).select_from(model))
            ).scalar() or 0
            after[label] = count

        print()
        print("== 清理后 ==")
        for k, v in after.items():
            print(f"  {k}: {v}")

        # 5. 抽样检查 account 重置情况
        rows = (await s.execute(select(VirtualAccount).limit(20))).scalars().all()
        print()
        print("== 账户余额校验(前 20 个) ==")
        for a in rows:
            ok = a.cash_balance == a.initial_capital and a.realized_pnl == 0
            mark = "✅" if ok else "❌"
            print(
                f"  {mark} id={a.id} user={a.user_id} market={a.market} "
                f"initial={a.initial_capital} cash={a.cash_balance} "
                f"realized={a.realized_pnl}",
            )


if __name__ == "__main__":
    asyncio.run(main())
