"""智能交易账户 provisioning(智能交易 PR-2)· 专属系统用户 + perp 虚拟账户(默认 10万U · 可改)。

照搬 managed/account.py 范式:智能交易账户 = 专属【系统用户】(intelligent-trading-bot · 不可登录)的
crypto perp 钱包。route_open_perp(user_id=智能系统user)自然解析到它,★引擎 100% 零碰。
金额可改/清零见 account_admin(通用)。🔴纯虚拟绝不真单。
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

# 系统用户(不可登录)· 智能交易账户挂在它名下
INTELLIGENT_BOT_EMAIL = "intelligent-trading-bot@system.midas.local"
INTELLIGENT_MARKET = "crypto"  # route_open_perp 走 _find_crypto_account 解析
INTELLIGENT_CURRENCY = "USDT"
INTELLIGENT_INITIAL_CAPITAL = Decimal("100000")  # 默认起始 10万 U(可改 · 见 account_admin)
# ★铂金多账户(PR-2):每铂金用户专属【影子系统用户】email 模板(intelligent-{真人uid}@...·不可登录)。
# ★全局 INTELLIGENT_BOT_EMAIL 保留不动(现在跑的智能交易用它 · 向后兼容 · 别破正在跑的)。
INTELLIGENT_BOT_EMAIL_TEMPLATE = "intelligent-{uid}@system.midas.local"


async def _ensure_bot_user(session: AsyncSession) -> User:
    """幂等 ensure 智能交易系统用户(★不可登录:无密码、无 google_sub)。"""
    user = await session.scalar(select(User).where(User.email == INTELLIGENT_BOT_EMAIL))
    if user is not None:
        return user
    user = User(
        email=INTELLIGENT_BOT_EMAIL,
        password_hash=None,   # ★无密码 → 不可密码登录
        google_sub=None,      # ★无 OAuth → 不可 OAuth 登录
        age_confirmed=True,
    )
    session.add(user)
    await session.flush()
    return user


async def ensure_intelligent_account(session: AsyncSession) -> VirtualAccount:
    """幂等 ensure 智能交易账户(系统用户 + crypto perp 钱包 · 默认 10万U)· 返回账户。

    已存在 → 复用(不重置资金 · 重置走 account_admin.reset_account)· 不存在 → 建。
    """
    user = await _ensure_bot_user(session)
    account = await session.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == user.id,
            VirtualAccount.market == INTELLIGENT_MARKET,
        ),
    )
    if account is not None:
        return account
    account = VirtualAccount(
        user_id=user.id,
        market=INTELLIGENT_MARKET,
        currency=INTELLIGENT_CURRENCY,
        initial_capital=INTELLIGENT_INITIAL_CAPITAL,
        cash_balance=INTELLIGENT_INITIAL_CAPITAL,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def get_intelligent_user_id(session: AsyncSession) -> UUID | None:
    """取智能交易系统用户 id(PR-4 开仓 route_open_perp(user_id=…) 用)· 未建则 None。"""
    uid: UUID | None = await session.scalar(
        select(User.id).where(User.email == INTELLIGENT_BOT_EMAIL),
    )
    return uid


# ── ★铂金多账户(PR-2):每铂金用户专属影子账户(全局版上方保留不动 · 这些是新增)──────


async def _ensure_bot_user_for_user(session: AsyncSession, user_id: UUID) -> User:
    """幂等 ensure 某铂金用户(真人 user_id)的专属【影子系统用户】(★不可登录:无密码/无 OAuth)。

    影子 email = intelligent-{真人uid}@... · 与真人用户隔离(真人自己的 crypto 账户互不影响)。
    """
    email = INTELLIGENT_BOT_EMAIL_TEMPLATE.format(uid=user_id)
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        return user
    user = User(email=email, password_hash=None, google_sub=None, age_confirmed=True)
    session.add(user)
    await session.flush()
    return user


async def ensure_intelligent_account_for_user(
    session: AsyncSession, user_id: UUID,
) -> VirtualAccount:
    """幂等 ensure 某铂金用户的专属智能交易影子账户(影子系统用户 + crypto perp 钱包 · 10万U)。

    ★route_open_perp(user_id=影子user.id) 自然解析到它 · 引擎零碰 · 与全局账户 + 真人账户全隔离。
    已存在 → 复用(不重置)· 不存在 → 建。PR-4 worker 遍历铂金用户时 lazy 调(幂等)。
    """
    user = await _ensure_bot_user_for_user(session, user_id)
    account = await session.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == user.id,
            VirtualAccount.market == INTELLIGENT_MARKET,
        ),
    )
    if account is not None:
        return account
    account = VirtualAccount(
        user_id=user.id,
        market=INTELLIGENT_MARKET,
        currency=INTELLIGENT_CURRENCY,
        initial_capital=INTELLIGENT_INITIAL_CAPITAL,
        cash_balance=INTELLIGENT_INITIAL_CAPITAL,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def get_intelligent_user_id_for_user(
    session: AsyncSession, user_id: UUID,
) -> UUID | None:
    """取某铂金用户的影子智能交易系统用户 id(PR-4 开/平 + PR-5 自助端点用)· 未建则 None。"""
    email = INTELLIGENT_BOT_EMAIL_TEMPLATE.format(uid=user_id)
    shadow_uid: UUID | None = await session.scalar(
        select(User.id).where(User.email == email),
    )
    return shadow_uid
