"""全仓(cross)账户级强平 pytest · ADR-0027 MC-3。

🔴 红线:全程虚拟资金 · 纯虚拟撮合数值校验。

测试矩阵(产品方逐项审):
- 纯函数:cross_equity / Σmm 数值 + 触发边界(=触发,+0.0001 不触发)
- 不触发(safe)/ 边界(=)/ 单仓触发 / 多仓一次性全平 / 多空混合
- 穿仓地板到 0(账户层勾稽:净亏=亏光开仓前 cash;单仓记真实值)
- 缺 mark → 跳过整账户(一仓不动)
- 🔴 事务原子性:中途某仓平仓抛错 → 全回滚,账户像没扫过
- 🔴 逐仓仓位不被误扫(同账户 isolated + cross,cross 触发 → 只平 cross)
- 🔴 跨账户隔离:只动传入账户

强平 worker 自身(取行情 + 单账户错误隔离 + 每账户 commit)自建 engine,
不在 test 事务内,故核心算法走 liquidate_cross_account(session,…) 充分覆盖。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import (
    MarginMode,
    PerpCloseReason,
    PerpSide,
    VirtualPerpPosition,
)
from app.models.virtual import VirtualAccount
from app.services.virtual_trading import perp_cross_liquidation as mod
from app.services.virtual_trading.perp_cross_liquidation import (
    STATUS_LIQUIDATED,
    STATUS_NO_POSITIONS,
    STATUS_SAFE,
    STATUS_SKIPPED_NO_MARK,
    cross_equity_and_maint,
    liquidate_cross_account,
    should_liquidate_cross,
)
from app.services.virtual_trading.perp_fees import q_money
from tests.factories import make_user, make_virtual_account


async def _account(db: AsyncSession, capital: str):
    user = await make_user(db)
    acct = await make_virtual_account(
        db, user_id=user.id, market="crypto", initial_capital=Decimal(capital),
    )
    await db.commit()
    return user, acct


async def _add_cross(
    db: AsyncSession, account_id: int, symbol: str, side: PerpSide,
    qty: str, entry: str, *, leverage: int = 10, mmr: str = "0.005",
) -> VirtualPerpPosition:
    """直接插一条 cross 活仓(精确控制 entry/qty · 全仓不划保证金,cash 不动)。"""
    q = Decimal(qty)
    e = Decimal(entry)
    pos = VirtualPerpPosition(
        account_id=account_id, symbol=symbol, side=side,
        margin_mode=MarginMode.CROSS, leverage=leverage,
        quantity=q, entry_price=e,
        initial_margin=q_money(q * e / Decimal(leverage)),
        maintenance_margin_rate=Decimal(mmr),
        liquidation_price=Decimal("0"),
    )
    db.add(pos)
    await db.flush()
    return pos


def _mem_pos(symbol: str, side: PerpSide, qty: str, entry: str, mmr: str = "0.005"):
    """内存 cross 仓位(只给纯函数读属性 · 不入库)。"""
    return VirtualPerpPosition(
        symbol=symbol, side=side, quantity=Decimal(qty),
        entry_price=Decimal(entry), maintenance_margin_rate=Decimal(mmr),
    )


async def _active_cross(db: AsyncSession, account_id: int) -> list[VirtualPerpPosition]:
    rows = await db.scalars(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account_id,
            VirtualPerpPosition.closed_at.is_(None),
            VirtualPerpPosition.margin_mode == MarginMode.CROSS,
        ),
    )
    return list(rows)


# ============================================================================
# 纯函数 · 权益 / 维持保证金 / 触发边界
# ============================================================================


def test_cross_equity_and_maint_values():
    # 1 多 BTC qty1 entry30000 mark29000 + 1 空 ETH qty10 entry2000 mark2100
    positions = [
        _mem_pos("BTCUSDT", PerpSide.LONG, "1", "30000"),
        _mem_pos("ETHUSDT", PerpSide.SHORT, "10", "2000"),
    ]
    marks = {"BTCUSDT": Decimal("29000"), "ETHUSDT": Decimal("2100")}
    equity, maint = cross_equity_and_maint(Decimal("5000"), positions, marks)
    # uPnL: long (29000-30000)*1=-1000 ; short (2000-2100)*10=-1000 → Σ=-2000
    # equity = 5000 - 2000 = 3000
    assert equity == Decimal("3000.0000")
    # mm = 29000*0.005 + 10*2100*0.005 = 145 + 105 = 250
    assert maint == Decimal("250.0000")


def test_should_liquidate_boundary():
    # 拍板:≤ 触发 · 相等触发,+0.0001 不触发
    assert should_liquidate_cross(Decimal("100.0000"), Decimal("100.0000")) is True
    assert should_liquidate_cross(Decimal("100.0001"), Decimal("100.0000")) is False
    assert should_liquidate_cross(Decimal("99.9999"), Decimal("100.0000")) is True


# ============================================================================
# 不触发 / 边界
# ============================================================================


@pytest.mark.asyncio
async def test_safe_not_triggered(db_session: AsyncSession):
    _u, acct = await _account(db_session, "10000")
    pos = await _add_cross(db_session, acct.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    await db_session.commit()

    outcome = await liquidate_cross_account(
        db_session, acct, {"BTCUSDT": Decimal("30000")},
    )
    assert outcome.status == STATUS_SAFE
    await db_session.refresh(pos)
    assert pos.closed_at is None  # 一仓没平
    await db_session.refresh(acct)
    assert acct.cash_balance == Decimal("10000.0000")


@pytest.mark.asyncio
async def test_boundary_equal_triggers_strictly_above_safe(db_session: AsyncSession):
    """equity 恰好 == mm → 触发;equity = mm + 0.0001 → safe(精确边界)。"""
    # entry30000 mark20000 qty1 → uPnL=-10000 ; mm=20000*0.005=100
    # equity = cash - 10000 ;要 equity==100 → cash=10100
    _u, acct_eq = await _account(db_session, "10100")
    await _add_cross(db_session, acct_eq.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    await db_session.commit()
    out_eq = await liquidate_cross_account(
        db_session, acct_eq, {"BTCUSDT": Decimal("20000")},
    )
    assert out_eq.status == STATUS_LIQUIDATED
    assert out_eq.equity == Decimal("100.0000")
    assert out_eq.maint_margin == Decimal("100.0000")

    # 同样仓位 · cash 多 0.0001 → equity 100.0001 > mm 100 → safe
    _u2, acct_safe = await _account(db_session, "10100.0001")
    await _add_cross(db_session, acct_safe.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    await db_session.commit()
    out_safe = await liquidate_cross_account(
        db_session, acct_safe, {"BTCUSDT": Decimal("20000")},
    )
    assert out_safe.status == STATUS_SAFE


# ============================================================================
# 触发:单仓 / 多仓 / 多空混合
# ============================================================================


@pytest.mark.asyncio
async def test_trigger_multi_positions_all_closed(db_session: AsyncSession):
    """2 个 cross 仓整体跌破 → 一次性全平 · 未穿仓(cash≥0)。"""
    # cash1600 · BTC long1@30000 mark29000(uPnL-1000)· ETH long10@2000 mark1950(uPnL-500)
    _u, acct = await _account(db_session, "1600")
    await _add_cross(db_session, acct.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    await _add_cross(db_session, acct.id, "ETHUSDT", PerpSide.LONG, "10", "2000")
    await db_session.commit()

    out = await liquidate_cross_account(
        db_session, acct,
        {"BTCUSDT": Decimal("29000"), "ETHUSDT": Decimal("1950")},
    )
    assert out.status == STATUS_LIQUIDATED
    assert out.liquidated_count == 2
    assert out.floored is False
    # equity = 1600 - 1500 = 100 ; mm = 145 + 97.5 = 242.5
    assert out.equity == Decimal("100.0000")
    assert out.maint_margin == Decimal("242.5000")
    # 两仓全平
    assert await _active_cross(db_session, acct.id) == []
    # cash:rn1=-1014.5 rn2=-509.75 Σ=-1524.25 → 1600-1524.25 = 75.75
    await db_session.refresh(acct)
    assert acct.cash_balance == Decimal("75.7500")
    assert acct.realized_pnl == Decimal("-1524.2500")


@pytest.mark.asyncio
async def test_trigger_long_short_mix(db_session: AsyncSession):
    """多空混合(BTC 多 + ETH 空)整体跌破 → 全平 · 空头用 (entry−exit)。"""
    # cash5100 · BTC long1@30000 mark26000(uPnL-4000)· ETH short10@2000 mark2100(uPnL-1000)
    _u, acct = await _account(db_session, "5100")
    await _add_cross(db_session, acct.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    await _add_cross(db_session, acct.id, "ETHUSDT", PerpSide.SHORT, "10", "2000")
    await db_session.commit()

    out = await liquidate_cross_account(
        db_session, acct,
        {"BTCUSDT": Decimal("26000"), "ETHUSDT": Decimal("2100")},
    )
    assert out.status == STATUS_LIQUIDATED
    assert out.liquidated_count == 2
    assert out.floored is False
    # equity = 5100 - 5000 = 100 ; mm = 130 + 105 = 235
    assert out.equity == Decimal("100.0000")
    assert out.maint_margin == Decimal("235.0000")
    assert await _active_cross(db_session, acct.id) == []
    # rn_long = (26000-30000) - 26000*0.0005 = -4000 - 13 = -4013
    # rn_short = (2000-2100)*10 - 21000*0.0005 = -1000 - 10.5 = -1010.5 ; Σ=-5023.5
    await db_session.refresh(acct)
    assert acct.cash_balance == Decimal("76.5000")  # 5100 - 5023.5
    assert acct.realized_pnl == Decimal("-5023.5000")


# ============================================================================
# 穿仓地板(DP-8 · 账户层勾稽)
# ============================================================================


@pytest.mark.asyncio
async def test_underwater_floor_to_zero(db_session: AsyncSession):
    """平完 cash<0 → 地板到 0;账户净亏=亏光开仓前 cash;单仓记真实值(差额=平台兜底)。"""
    # cash500 · BTC long1@30000 mark25000(uPnL-5000)
    _u, acct = await _account(db_session, "500")
    pos = await _add_cross(db_session, acct.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    await db_session.commit()

    out = await liquidate_cross_account(
        db_session, acct, {"BTCUSDT": Decimal("25000")},
    )
    assert out.status == STATUS_LIQUIDATED
    assert out.floored is True
    await db_session.refresh(acct)
    # cash 地板到 0,账户 realized_pnl = -pre_cash = -500(净亏封顶=亏光钱包)
    assert acct.cash_balance == Decimal("0.0000")
    assert acct.realized_pnl == Decimal("-500.0000")
    # 单仓 position.realized_pnl 记真实:gross-fee = -5000 - 12.5 = -5012.5
    await db_session.refresh(pos)
    assert pos.realized_pnl == Decimal("-5012.5000")
    assert pos.closed_at is not None
    assert pos.close_reason == PerpCloseReason.LIQUIDATED
    # 平台兜底 = 单仓真实亏 − 账户记账亏 = |−5012.5| − |−500| = 4512.5
    assert (pos.realized_pnl - acct.realized_pnl) == Decimal("-4512.5000")


# ============================================================================
# 缺 mark → 跳过整账户
# ============================================================================


@pytest.mark.asyncio
async def test_skip_when_any_mark_missing(db_session: AsyncSession):
    """2 仓里 ETH 缺 mark → 跳过整账户,两仓全不动(宁可不平)。"""
    _u, acct = await _account(db_session, "500")
    p1 = await _add_cross(db_session, acct.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    p2 = await _add_cross(db_session, acct.id, "ETHUSDT", PerpSide.LONG, "10", "2000")
    await db_session.commit()

    # 只给 BTC 的 mark(本应触发强平),ETH 缺 → 整账户跳过
    out = await liquidate_cross_account(
        db_session, acct, {"BTCUSDT": Decimal("25000")},
    )
    assert out.status == STATUS_SKIPPED_NO_MARK
    await db_session.refresh(p1)
    await db_session.refresh(p2)
    assert p1.closed_at is None
    assert p2.closed_at is None
    await db_session.refresh(acct)
    assert acct.cash_balance == Decimal("500.0000")


@pytest.mark.asyncio
async def test_no_positions(db_session: AsyncSession):
    _u, acct = await _account(db_session, "10000")
    out = await liquidate_cross_account(db_session, acct, {})
    assert out.status == STATUS_NO_POSITIONS


# ============================================================================
# 🔴 事务原子性:中途某仓平仓抛错 → 全回滚
# ============================================================================


@pytest.mark.asyncio
async def test_atomicity_rollback_on_midway_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """触发后全平过程中第 2 仓抛错 → 整账户回滚,像没扫过(铁律:绝无半成品)。"""
    _u, acct = await _account(db_session, "500")
    await _add_cross(db_session, acct.id, "AAAUSDT", PerpSide.LONG, "1", "30000")
    await _add_cross(db_session, acct.id, "BBBUSDT", PerpSide.LONG, "1", "30000")
    await db_session.commit()
    cash_before = acct.cash_balance

    orig = mod._liquidate_one
    calls = {"n": 0}

    async def _faulty(session, pos, mark):  # noqa: ANN001, ANN202
        calls["n"] += 1
        if calls["n"] == 2:  # 第 2 仓平仓时炸
            raise RuntimeError("boom on 2nd position")
        return await orig(session, pos, mark)

    monkeypatch.setattr(mod, "_liquidate_one", _faulty)

    marks = {"AAAUSDT": Decimal("25000"), "BBBUSDT": Decimal("25000")}
    # 用自己的 SAVEPOINT 包住:第 2 仓抛错时,async 上下文管理器干净回滚该 savepoint
    #(已平的第 1 仓 + 账户改动全部撤销),模拟 worker 的 try/except: rollback。
    with pytest.raises(RuntimeError, match="boom on 2nd"):
        async with db_session.begin_nested():
            await liquidate_cross_account(db_session, acct, marks)

    # 账户状态完全回到强平前:两仓仍活、cash 没变(绝无"平了一半"的半成品)
    still_active = await _active_cross(db_session, acct.id)
    assert len(still_active) == 2
    assert all(p.closed_at is None for p in still_active)
    acct_after = await db_session.scalar(
        select(VirtualAccount).where(VirtualAccount.id == acct.id),
    )
    assert acct_after is not None
    assert acct_after.cash_balance == cash_before


# ============================================================================
# 🔴 逐仓不被误扫 + 跨账户隔离
# ============================================================================


@pytest.mark.asyncio
async def test_isolated_position_untouched_when_cross_liquidates(
    db_session: AsyncSession,
):
    """同账户 isolated(ETH)+ cross(BTC),cross 触发强平 → 只平 cross,逐仓毫发无损。"""
    from app.services.virtual_trading.perp_engine import (
        OpenPerpRequest,
        open_perp_position,
    )
    from tests.factories import make_perp_price_fetcher

    _u, acct = await _account(db_session, "2000")
    # 逐仓 ETH(走逐仓引擎 · 划出保证金)
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=_u.id, symbol="ETHUSDT", side=PerpSide.LONG,
            leverage=5, quantity=Decimal("0.1"),
        ),
        make_perp_price_fetcher({"ETHUSDT": Decimal("2000")}),
    )
    await db_session.commit()
    iso = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acct.id,
            VirtualPerpPosition.margin_mode == MarginMode.ISOLATED,
        ),
    )
    assert iso is not None
    iso_margin_before = iso.initial_margin
    iso_liq_before = iso.liquidation_price

    # cross BTC 深度浮亏
    await _add_cross(db_session, acct.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    await db_session.commit()

    out = await liquidate_cross_account(
        db_session, acct, {"BTCUSDT": Decimal("25000")},
    )
    assert out.status == STATUS_LIQUIDATED
    assert out.liquidated_count == 1  # 只平了 cross 那 1 个

    # 🔴 逐仓 ETH 仓:活仓、保证金、强平价 全部纹丝不动
    await db_session.refresh(iso)
    assert iso.closed_at is None
    assert iso.margin_mode == MarginMode.ISOLATED
    assert iso.initial_margin == iso_margin_before
    assert iso.liquidation_price == iso_liq_before
    # cross BTC 已平
    assert await _active_cross(db_session, acct.id) == []


@pytest.mark.asyncio
async def test_cross_account_isolation(db_session: AsyncSession):
    """A 触发强平,B 账户 cross 仓位 + cash 完全不变。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    acct_a = await make_virtual_account(
        db_session, user_id=user_a.id, market="crypto", initial_capital=Decimal("500"),
    )
    acct_b = await make_virtual_account(
        db_session, user_id=user_b.id, market="crypto", initial_capital=Decimal("500"),
    )
    await db_session.commit()
    await _add_cross(db_session, acct_a.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    p_b = await _add_cross(db_session, acct_b.id, "BTCUSDT", PerpSide.LONG, "1", "30000")
    await db_session.commit()
    cash_b_before = acct_b.cash_balance

    out = await liquidate_cross_account(
        db_session, acct_a, {"BTCUSDT": Decimal("25000")},
    )
    assert out.status == STATUS_LIQUIDATED
    # B 完全不变
    await db_session.refresh(acct_b)
    await db_session.refresh(p_b)
    assert acct_b.cash_balance == cash_b_before
    assert p_b.closed_at is None
    assert len(await _active_cross(db_session, acct_b.id)) == 1
