"""测试 fixtures · 异步工厂函数(无 factory_boy,避免 async 配合不顺)。

约定:
- 所有 `make_*` 函数收 `db: AsyncSession` + 关键字 overrides
- 自动 flush() 让 ORM 拿到 PK,但不 commit(让外层 SAVEPOINT 控制)
- 邮箱 / token 等用 secrets 随机生成,避免 UniqueConstraint 冲突
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.verification_token import TokenPurpose, VerificationToken
from app.models.watchlist import WatchlistItem
from app.services.auth import hash_password

if TYPE_CHECKING:
    from app.models.virtual import VirtualAccount
    from app.services.virtual_trading.engine import PriceFetcher


def random_email() -> str:
    return f"test-{secrets.token_hex(4)}@midas.example"


def random_password() -> str:
    return secrets.token_urlsafe(12)


async def make_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    password: str = "testpass1234",
    email_verified: bool = True,
    age_confirmed: bool = True,
    demo_prefilled: bool = False,
    **overrides: Any,
) -> User:
    """造一个 user · 默认已验证邮箱 + 18+。

    返回 User 实例(已 flush 拿到 id,但未 commit)。
    """
    user = User(
        email=email or random_email(),
        password_hash=hash_password(password),
        age_confirmed=age_confirmed,
        email_verified_at=datetime.now(UTC) if email_verified else None,
        demo_prefilled=demo_prefilled,
        **overrides,
    )
    db.add(user)
    await db.flush()
    return user


async def make_unverified_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    password: str = "testpass1234",
) -> User:
    return await make_user(
        db, email=email, password=password, email_verified=False,
    )


async def make_verification_token(
    db: AsyncSession,
    *,
    user_id: UUID,
    purpose: TokenPurpose = TokenPurpose.EMAIL_VERIFICATION,
    expired: bool = False,
    consumed: bool = False,
) -> VerificationToken:
    expires_at = (
        datetime.now(UTC) - timedelta(hours=1)
        if expired
        else datetime.now(UTC) + timedelta(hours=24)
    )
    consumed_at = datetime.now(UTC) if consumed else None
    token = VerificationToken(
        token=secrets.token_urlsafe(48),
        user_id=user_id,
        purpose=purpose,
        expires_at=expires_at,
        consumed_at=consumed_at,
    )
    db.add(token)
    await db.flush()
    return token


async def make_watchlist_item(
    db: AsyncSession,
    *,
    user_id: UUID,
    symbol: str = "NVDA",
    market: str = "us",
    sort_order: int = 0,
) -> WatchlistItem:
    item = WatchlistItem(
        user_id=user_id,
        symbol=symbol,
        market=market,
        sort_order=sort_order,
    )
    db.add(item)
    await db.flush()
    return item


# ===== 虚拟交易 fixtures =====


async def make_virtual_account(
    db: AsyncSession,
    *,
    user_id: UUID,
    market: str = "us",
    initial_capital: Decimal = Decimal("100000"),
) -> VirtualAccount:
    from app.models.virtual import MARKET_CURRENCY, VirtualAccount

    account = VirtualAccount(
        user_id=user_id,
        market=market,
        currency=MARKET_CURRENCY[market],
        initial_capital=initial_capital,
        cash_balance=initial_capital,
    )
    db.add(account)
    await db.flush()
    return account


def make_static_price_fetcher(
    prices: dict[tuple[str, str], Decimal | None],
) -> PriceFetcher:
    """造一个固定价 fetcher · 给 engine 测试用 · key 是 (symbol, market)。"""

    async def fetcher(symbol: str, market: str) -> Decimal | None:
        return prices.get((symbol, market))

    return fetcher


def make_perp_price_fetcher(
    prices: dict[str, Decimal | None],
) -> Callable[[str], Awaitable[Decimal | None]]:
    """造一个固定价 perp fetcher · 给 perp_engine 测试用 · key 是 symbol(Binance 风格)。"""

    async def fetcher(symbol: str) -> Decimal | None:
        return prices.get(symbol)

    return fetcher
