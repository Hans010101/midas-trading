"""托管交易账户 provisioning(托管交易 PR-1)· 专属系统用户 + perp 虚拟账户(10万U)。

★方案B(Step 0 发现方案A 要碰引擎后修订 · Hans 拍板):托管账户 = 专属【系统用户】的 crypto perp
钱包。这样 route_open_perp(user_id=托管系统user)自然解析到它,★引擎(route_open_perp /
open_cross_position / _find_crypto_account)100% 零碰。独立性靠专属 user_id。

系统用户:固定 email · password_hash=None + google_sub=None → ★不可登录(无密码、无 OAuth)。
幂等:已存在则复用,不存在则建(开关首次开启 / 启动时调)。🔴纯虚拟绝不真单。
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.user import User
from app.models.virtual import VirtualAccount

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

# 系统用户(不可登录)· 托管账户挂在它名下
MANAGED_BOT_EMAIL = "managed-trading-bot@system.midas.local"
# 托管 perp 账户:market="crypto"(route_open_perp 走 _find_crypto_account 解析)· USDT 钱包
MANAGED_MARKET = "crypto"
MANAGED_CURRENCY = "USDT"
MANAGED_INITIAL_CAPITAL = Decimal("100000")  # 起始 10 万 U 虚拟


async def _ensure_bot_user(session: AsyncSession) -> User:
    """幂等 ensure 托管系统用户(★不可登录:无密码、无 google_sub)。"""
    user = await session.scalar(select(User).where(User.email == MANAGED_BOT_EMAIL))
    if user is not None:
        return user
    user = User(
        email=MANAGED_BOT_EMAIL,
        password_hash=None,   # ★无密码 → 不可密码登录
        google_sub=None,      # ★无 OAuth → 不可 OAuth 登录
        age_confirmed=True,   # 系统账户 · 跳过年龄门
    )
    session.add(user)
    await session.flush()  # 拿 user.id 给账户用(同事务)
    return user


async def ensure_managed_account(session: AsyncSession) -> VirtualAccount:
    """幂等 ensure 托管账户(系统用户 + 其 crypto perp 钱包 10万U)· 返回账户。

    已存在 → 复用(不重置资金)· 不存在 → 建。开关首次开启 / worker 启动时调。
    """
    user = await _ensure_bot_user(session)
    account = await session.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == user.id,
            VirtualAccount.market == MANAGED_MARKET,
        ),
    )
    if account is not None:
        return account
    account = VirtualAccount(
        user_id=user.id,
        market=MANAGED_MARKET,
        currency=MANAGED_CURRENCY,
        initial_capital=MANAGED_INITIAL_CAPITAL,
        cash_balance=MANAGED_INITIAL_CAPITAL,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def get_managed_user_id(session: AsyncSession) -> UUID | None:
    """取托管系统用户 id(PR-2 开仓编排 route_open_perp(user_id=…) 用)· 未建则 None。"""
    uid: UUID | None = await session.scalar(
        select(User.id).where(User.email == MANAGED_BOT_EMAIL),
    )
    return uid
