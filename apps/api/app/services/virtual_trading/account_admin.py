"""虚拟账户管理(金额可改 / 清零重来)· 智能交易 + 托管交易【通用】(智能交易 PR-2)。

🔴 ★只操作【指定账户】:删该账户 perp 持仓+历史 + 重置 cash/realized · 不碰引擎/其他账户。
清零是 admin 重置前向测试数据(直接 DB 删 + 改 cash · 非撮合 · 引擎零碰)· 用 account_id 严格过滤。
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete

from app.models.perp import VirtualPerpPosition

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.virtual import VirtualAccount


async def reset_account(session: AsyncSession, account: VirtualAccount) -> int:
    """清零重来:删该账户【所有 perp 持仓 + 历史】+ cash 重置到 initial_capital + realized 清零。

    ★只删 account_id == account.id 的仓(不碰其他账户/引擎)· 返回删除仓位数。
    """
    result = await session.execute(
        delete(VirtualPerpPosition).where(VirtualPerpPosition.account_id == account.id),
    )
    account.cash_balance = account.initial_capital
    account.realized_pnl = Decimal("0")
    await session.commit()
    return int(cast("CursorResult[Any]", result).rowcount or 0)


async def set_account_capital(
    session: AsyncSession, account: VirtualAccount, amount: Decimal,
) -> int:
    """改起始资金:initial_capital + cash = amount + realized 清零 + ★清持仓(用新资金重来)。

    amount 必须 > 0(调用方校验)· 返回删除仓位数。★只该账户。
    """
    result = await session.execute(
        delete(VirtualPerpPosition).where(VirtualPerpPosition.account_id == account.id),
    )
    account.initial_capital = amount
    account.cash_balance = amount
    account.realized_pnl = Decimal("0")
    await session.commit()
    return int(cast("CursorResult[Any]", result).rowcount or 0)
