"""测试 fixtures · 异步工厂函数(无 factory_boy,避免 async 配合不顺)。

约定:
- 所有 `make_*` 函数收 `db: AsyncSession` + 关键字 overrides
- 自动 flush() 让 ORM 拿到 PK,但不 commit(让外层 SAVEPOINT 控制)
- 邮箱 / token 等用 secrets 随机生成,避免 UniqueConstraint 冲突
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.verification_token import TokenPurpose, VerificationToken
from app.models.watchlist import WatchlistItem
from app.services.auth import hash_password
from app.services.backtest.types import BacktestParams, BacktestResult

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


# ===== 研究室回测 fixtures(P1-4c.5)=====


def make_backtest_result(params: BacktestParams) -> BacktestResult:
    """造一个完整 BacktestResult(16 指标 + 2 个 equity 点 + 1 笔 trade + run_card)。

    persist_result 扩写 / 读端点 full-data 测试共用 · 字段形状对齐 service.parse_artifacts 产出。
    """
    return {
        "params": asdict(params),
        "metrics": {
            "final_value": 1_100_000.0,
            "total_return": 0.1,
            "annual_return": 0.08,
            "max_drawdown": -0.05,
            "sharpe": 1.2,
            "calmar": 1.6,
            "sortino": 1.8,
            "win_rate": 0.55,
            "profit_loss_ratio": 1.3,
            "profit_factor": 1.4,
            "max_consecutive_loss": 3,
            "avg_holding_days": 4.5,
            "trade_count": 12,
            "benchmark_return": 0.06,
            "excess_return": 0.04,
            "information_ratio": 0.9,
        },
        "equity": [
            {
                "timestamp": "2025-01-17",
                "equity": 1_000_000.0,
                "drawdown": 0.0,
                "benchmark_equity": 1_000_000.0,
                "ret": 0.0,
                "active_ret": 0.0,
            },
            {
                "timestamp": "2025-01-18",
                "equity": 1_010_000.0,
                "drawdown": 0.0,
                "benchmark_equity": 1_005_000.0,
                "ret": 0.01,
                "active_ret": 0.005,
            },
        ],
        "trades": [
            {
                "timestamp": "2025-01-18",
                "code": "BTCUSDT",
                "side": "buy",
                "price": 95_000.0,
                "qty": 0.1,
                "reason": "entry",
                "pnl": 0.0,
                "holding_days": 0.0,
                "return_pct": 0.0,
            },
        ],
        "run_card": {"data_sources": ["ccxt"], "reproducibility": {"config_hash": "abc"}},
    }
