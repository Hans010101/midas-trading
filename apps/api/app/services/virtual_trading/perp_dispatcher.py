"""加密永续 · 接入分流层(ADR-0027 MC-4)· 仅做路由,绝不含撮合逻辑。

调用层(路由 / bot facade)统一走本模块,按 (margin_mode 偏好 + 现有活仓 mode)
分流到逐仓引擎(perp_engine)或全仓引擎(perp_cross_engine)。引擎核心一行不改。

🔴 分流规则(严守 DP-7 同 symbol 单一模式):
- flat(无活仓)→ 按 preferred(用户偏好 · 来自 preset / 下单请求)开新仓。
- 已有活仓 → 按 **活仓 margin_mode** 走对应引擎;
  · 若 preferred ≠ 活仓 mode → **拒单**(写入 REJECTED 流水 + 清晰文案),
    防止把 cross 仓送进逐仓引擎(perp_engine 没 mode 守卫,会按 isolated 误算)。
- 平仓:按活仓 mode 分流;无活仓 → 拒(交给被调引擎给标准文案)。

🚫 隔离红线:
- 不修改 perp_engine / perp_cross_engine 任何字符;只调它们的公开 API。
- 不复用任何 _internal 函数;DTO(OpenPerpRequest / OpenCrossRequest / Close*)
  按对应引擎的契约构造。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import (
    MarginMode,
    OrderStatus,
    PerpAction,
    PerpSide,
    VirtualPerpOrder,
    VirtualPerpPosition,
)
from app.services.virtual_trading.perp_cross_engine import (
    CloseCrossRequest,
    OpenCrossRequest,
    PerpPriceFetcher,
    close_cross_position,
    open_cross_position,
)
from app.services.virtual_trading.perp_engine import (
    ClosePerpRequest,
    OpenPerpRequest,
    close_perp_position,
    open_perp_position,
)

_ZERO = Decimal("0")


async def _active_position(
    db: AsyncSession, user_id: UUID, symbol: str,
) -> VirtualPerpPosition | None:
    """查该用户该 symbol 的 cross 活仓(查询自带 user 隔离 · join account → user)。

    用 join 而非两步查 · 一次往返。不锁(分流前的只读判定 · 引擎里会再 FOR UPDATE)。
    """
    from app.models.virtual import VirtualAccount  # 局部 import 避免循环

    pos: VirtualPerpPosition | None = await db.scalar(
        select(VirtualPerpPosition)
        .join(VirtualAccount, VirtualPerpPosition.account_id == VirtualAccount.id)
        .where(
            VirtualAccount.user_id == user_id,
            VirtualAccount.market == "crypto",
            VirtualPerpPosition.symbol == symbol,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    return pos


def _reject_mode_conflict(
    *, symbol: str, active_mode: str, preferred_mode: str, action: PerpAction,
    quantity: Decimal, leverage: int | None,
) -> VirtualPerpOrder:
    """偏好与活仓模式不一致 · 拒单(REJECTED 流水)· DP-7。

    返回未持久化的 sentinel 订单(account_id=0)· 调用方按 status == REJECTED 处理,
    与现有 perp_engine._record_rejected(account_id=None)路径一致。
    """
    active_label = "全仓" if active_mode == MarginMode.CROSS else "逐仓"
    pref_label = "全仓" if preferred_mode == MarginMode.CROSS else "逐仓"
    return VirtualPerpOrder(
        account_id=0, symbol=symbol, action=action,
        quantity=quantity, leverage=leverage,
        status=OrderStatus.REJECTED,
        reject_reason=(
            f"该 symbol 已有【{active_label}】活仓 · 偏好【{pref_label}】与之不一致 · "
            "请先平仓再切换保证金模式(DP-7 同 symbol 单一模式)"
        ),
        is_liquidation=False,
    )


# ============================================================================
# 开仓接入(对外唯一开仓入口 · 路由 / bot facade 都走它)
# ============================================================================


async def route_open_perp(
    db: AsyncSession,
    *,
    user_id: UUID,
    symbol: str,
    side: PerpSide,
    leverage: int,
    margin: Decimal | None,
    quantity: Decimal | None,
    preferred_mode: MarginMode,
    get_mark_price: PerpPriceFetcher,
) -> VirtualPerpOrder:
    """按 preferred_mode + 现有活仓 mode 分流。引擎内部处理 fresh/add/reverse。

    身份隔离:user_id 由调用方从已验证身份取(网页 token / bot 绑定),仅落到对应账户。
    """
    active = await _active_position(db, user_id, symbol)
    if active is not None and active.margin_mode != preferred_mode:
        action = (
            PerpAction.OPEN_LONG if side == PerpSide.LONG else PerpAction.OPEN_SHORT
        )
        return _reject_mode_conflict(
            symbol=symbol, active_mode=active.margin_mode,
            preferred_mode=preferred_mode, action=action,
            quantity=quantity or _ZERO, leverage=leverage,
        )

    # 有活仓 → 按活仓 mode(保证 cross 仓永不进逐仓引擎,反之亦然)
    # flat → 按偏好
    target_mode = active.margin_mode if active is not None else preferred_mode

    if target_mode == MarginMode.CROSS:
        return await open_cross_position(
            db,
            OpenCrossRequest(
                user_id=user_id, symbol=symbol, side=side, leverage=leverage,
                margin=margin, quantity=quantity,
            ),
            get_mark_price,
        )
    return await open_perp_position(
        db,
        OpenPerpRequest(
            user_id=user_id, symbol=symbol, side=side, leverage=leverage,
            margin=margin, quantity=quantity,
        ),
        get_mark_price,
    )


# ============================================================================
# 平仓接入(对外唯一平仓入口)
# ============================================================================


async def route_close_perp(
    db: AsyncSession,
    *,
    user_id: UUID,
    symbol: str,
    quantity: Decimal | None,
    close_all: bool,
    get_mark_price: PerpPriceFetcher,
) -> VirtualPerpOrder:
    """按【活仓 mode】分流到对应引擎的 close_*_position。无活仓 → 走 isolated 引擎给标准拒单。"""
    active = await _active_position(db, user_id, symbol)
    if active is not None and active.margin_mode == MarginMode.CROSS:
        return await close_cross_position(
            db,
            CloseCrossRequest(
                user_id=user_id, symbol=symbol,
                quantity=quantity, close_all=close_all,
            ),
            get_mark_price,
        )
    # 活仓是 isolated,或无活仓(让 perp_engine 给"无活仓可平"标准拒单)
    return await close_perp_position(
        db,
        ClosePerpRequest(
            user_id=user_id, symbol=symbol, quantity=quantity, close_all=close_all,
        ),
        get_mark_price,
    )
