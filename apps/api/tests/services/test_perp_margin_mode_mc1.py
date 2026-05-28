"""MC-1(ADR-0027)· margin_mode 改 String + 逐仓强平 worker 隔离过滤 · 零回归证明。

本文件【不】测任何全仓逻辑(全仓开仓/计算/强平在 MC-2/3/4)。只锁三件事:
1. 引擎开仓后 margin_mode 落库为小写 'isolated'(StrEnum→String 往返 · 与 worker 过滤对齐)。
2. 🔴 逐仓强平 worker 的过滤谓词:现有逐仓仓位【依旧全部入选】(零回归),
   而预置的全仓('cross')仓位被排除(隔离生效 · 防被逐仓 per-position liq 误杀)。
3. 现网「全 isolated」场景下,加过滤前后扫描集合【完全一致】(零行为变化)。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.services.virtual_trading.perp_engine import (
    OpenPerpRequest,
    open_perp_position,
)
from tests.factories import (
    make_perp_price_fetcher,
    make_user,
    make_virtual_account,
)


async def _crypto_account(db: AsyncSession):
    user = await make_user(db)
    account = await make_virtual_account(
        db, user_id=user.id, market="crypto", initial_capital=Decimal("100000"),
    )
    await db.commit()
    return user, account


def _isolated_only(
    stmt: Select[tuple[VirtualPerpPosition]],
) -> Select[tuple[VirtualPerpPosition]]:
    """逐仓 worker 加过滤【之后】的扫描谓词(与 perp_liquidation._scan 一致)。"""
    return stmt.where(
        VirtualPerpPosition.closed_at.is_(None),
        VirtualPerpPosition.margin_mode == MarginMode.ISOLATED,
    )


def _all_active(
    stmt: Select[tuple[VirtualPerpPosition]],
) -> Select[tuple[VirtualPerpPosition]]:
    """逐仓 worker 加过滤【之前】的旧扫描谓词(只看活仓)。"""
    return stmt.where(VirtualPerpPosition.closed_at.is_(None))


@pytest.mark.asyncio
async def test_engine_open_writes_lowercase_isolated(db_session: AsyncSession):
    """引擎开仓 → margin_mode 落库 'isolated'(小写)· 且 == MarginMode.ISOLATED。"""
    user, account = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        fetcher,
    )
    await db_session.commit()

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert pos is not None
    # String 列存的是 StrEnum 的 .value(小写)· 与迁移归一后的存量行一致
    assert pos.margin_mode == "isolated"
    assert pos.margin_mode == MarginMode.ISOLATED


@pytest.mark.asyncio
async def test_liquidation_filter_includes_isolated_excludes_cross(
    db_session: AsyncSession,
):
    """🔴 零回归核心:worker 过滤后,逐仓仓位全入选、全仓仓位被排除。"""
    _user, account = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    # 1) 引擎开一个真实【逐仓】仓(margin_mode='isolated')—— 代表现网存量
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=_user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        fetcher,
    )
    # 2) 直接预置一个【全仓】活仓(模拟 MC-2+ 未来数据 · 本期引擎不会产出)
    db_session.add(
        VirtualPerpPosition(
            account_id=account.id, symbol="ETHUSDT", side=PerpSide.SHORT,
            margin_mode=MarginMode.CROSS,
            leverage=5, quantity=Decimal("1"), entry_price=Decimal("2000"),
            initial_margin=Decimal("400"),
            maintenance_margin_rate=Decimal("0.005"),
            liquidation_price=Decimal("2360"),
        ),
    )
    await db_session.commit()

    base = select(VirtualPerpPosition).where(
        VirtualPerpPosition.account_id == account.id,
    )
    isolated_scan = (await db_session.scalars(_isolated_only(base))).all()
    all_scan = (await db_session.scalars(_all_active(base))).all()

    iso_symbols = {p.symbol for p in isolated_scan}
    all_symbols = {p.symbol for p in all_scan}

    # 逐仓仓【依旧入选】(零回归 · 该强平的照常被扫到)
    assert "BTCUSDT" in iso_symbols
    # 全仓仓【被排除】(隔离 · 不会被逐仓 per-position liq 误杀)
    assert "ETHUSDT" not in iso_symbols
    assert isolated_scan  # 至少扫到那条逐仓
    assert all(p.margin_mode == MarginMode.ISOLATED for p in isolated_scan)
    # 旧谓词会把全仓也扫进来(对照:证明差异恰好就是那条 cross 仓)
    assert "ETHUSDT" in all_symbols
    assert all_symbols - iso_symbols == {"ETHUSDT"}


@pytest.mark.asyncio
async def test_all_isolated_env_filter_is_noop(db_session: AsyncSession):
    """现网「全逐仓」场景:加过滤前后扫描集合完全一致(零行为变化)。"""
    _user, account = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher(
        {"BTCUSDT": Decimal("30000"), "SOLUSDT": Decimal("150")},
    )
    for sym in ("BTCUSDT", "SOLUSDT"):
        await open_perp_position(
            db_session,
            OpenPerpRequest(
                user_id=_user.id, symbol=sym, side=PerpSide.LONG,
                leverage=5, quantity=Decimal("1"),
            ),
            fetcher,
        )
    await db_session.commit()

    base = select(VirtualPerpPosition).where(
        VirtualPerpPosition.account_id == account.id,
    )
    isolated_scan = {p.id for p in (await db_session.scalars(_isolated_only(base))).all()}
    all_scan = {p.id for p in (await db_session.scalars(_all_active(base))).all()}

    # 没有任何 cross 行时,新旧谓词命中完全相同 —— 现网零回归
    assert isolated_scan == all_scan
    assert len(isolated_scan) == 2
