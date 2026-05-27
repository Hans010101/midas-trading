"""自选股路由 · /api/v1/watchlist/*

0007 扁平结构(无 group 层),全部按 user_id 强隔离。

- GET    /watchlist            · 当前用户全部自选(空且 email_verified → 预填 3 demo)
- POST   /watchlist            · 加一个自选(409 if 同 user/symbol/market 已存在)
- DELETE /watchlist/{id}       · 删一个(404 if 不存在 / 不属于当前用户)
- PUT    /watchlist/reorder    · 单事务批量改 sort_order
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.models.watchlist import WatchlistItem
from app.schemas.watchlist import (
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistReorderIn,
)
from app.services.data_sources.crypto_source import CcxtBinanceCryptoSource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _get_crypto_source_optional(request: Request) -> CcxtBinanceCryptoSource | None:
    """加自选 crypto 存在性校验用 · 取 lifespan 注入的 crypto 源。

    无 lifespan(watchlist 单测 / 启动未完成)→ None · 此时跳过校验(fail-open),
    保证单测无需 ccxt 也能跑、且绝不误伤 A股/美股加自选。
    """
    return getattr(request.app.state, "crypto_source", None)


# Optional:无 lifespan 时为 None(不像 deps.CryptoSourceDep 那样硬取 app.state)
OptionalCryptoSourceDep = Annotated[
    CcxtBinanceCryptoSource | None, Depends(_get_crypto_source_optional),
]


# 首次登录预填三市场代表标的(0007 第 6 节)
# 顺序固定:加密在最上(变动最频繁,看着像「活着的产品」)→ 美股 → A 股
DEMO_WATCHLIST: tuple[tuple[str, Literal["cn", "us", "crypto"]], ...] = (
    ("BTC/USDT", "crypto"),
    ("NVDA", "us"),
    ("600519", "cn"),
)


# =====================
# 内部 helper
# =====================


async def _list_items_sorted(
    db: AsyncSession, *, user_id: object,
) -> list[WatchlistItem]:
    """查当前用户全部自选,按 sort_order ASC,然后 added_at ASC 兜底。"""
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.added_at.asc()),
    )
    return list(result.scalars().all())


async def _prefill_demo(db: AsyncSession, *, user_id: object) -> None:
    """空 watchlist + 已验证邮箱 → 一次性插入 3 demo symbols。

    用 PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` 兜底并发竞争。
    """
    rows = [
        {
            "user_id": user_id,
            "symbol": symbol,
            "market": market,
            "sort_order": i,
        }
        for i, (symbol, market) in enumerate(DEMO_WATCHLIST)
    ]
    stmt = pg_insert(WatchlistItem).values(rows).on_conflict_do_nothing(
        constraint="uq_watchlist_user_symbol",
    )
    await db.execute(stmt)
    await db.commit()
    logger.info(
        "[watchlist.prefill] user_id=%s 预填 %d demo symbols",
        user_id, len(rows),
    )


# =====================
# 路由
# =====================


@router.get(
    "",
    response_model=list[WatchlistItemResponse],
    summary="当前用户的自选股列表",
    description=(
        "首次访问(列表为空 + 邮箱已验证 + 未预填过)→ 自动预填 3 个跨市场 demo symbols。"
        "用户主动清空 watchlist 后不会再触发(demo_prefilled 标志已置 true)。"
    ),
)
async def list_watchlist(
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[WatchlistItemResponse]:
    items = await _list_items_sorted(db, user_id=current_user.id)
    if (
        not items
        and current_user.email_verified_at is not None
        and not current_user.demo_prefilled
    ):
        await _prefill_demo(db, user_id=current_user.id)
        current_user.demo_prefilled = True
        await db.commit()
        items = await _list_items_sorted(db, user_id=current_user.id)
    return [WatchlistItemResponse.model_validate(it) for it in items]


@router.post(
    "",
    response_model=WatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="加一个自选",
)
async def add_watchlist(
    payload: WatchlistItemCreate,
    current_user: CurrentUserDep,
    db: DbDep,
    crypto_source: OptionalCryptoSourceDep,
) -> WatchlistItemResponse:
    # 1. 重复检测
    existing = await db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.symbol == payload.symbol,
            WatchlistItem.market == payload.market,
        ),
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该标的已在自选列表",
        )

    # 2. 加密标的存在性校验(仅 crypto · A股/美股保持原逻辑、不校验)。
    #    查内存交易对表(lifespan 预载 · 见 crypto_source.symbol_exists)· 不打实时上游。
    #    crypto_source 为 None(无 lifespan / 预载未完成)→ 跳过(fail-open),不阻塞加入。
    if (
        payload.market == "crypto"
        and crypto_source is not None
        and not crypto_source.symbol_exists(payload.symbol)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"加密交易对不存在:{payload.symbol}(请用 Binance 现货交易对,如 BTC/USDT)",
        )

    # 3. 算 sort_order = max + 1(或 0 如果列表为空)
    max_order = await db.scalar(
        select(func.coalesce(func.max(WatchlistItem.sort_order), -1))
        .where(WatchlistItem.user_id == current_user.id),
    )

    new_item = WatchlistItem(
        user_id=current_user.id,
        symbol=payload.symbol,
        market=payload.market,
        sort_order=int(max_order or -1) + 1,
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)
    return WatchlistItemResponse.model_validate(new_item)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删一个自选",
)
async def delete_watchlist(
    item_id: int,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    result = await db.execute(
        delete(WatchlistItem)
        .where(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == current_user.id,
        )
        .returning(WatchlistItem.id),
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="自选股不存在或无权限",
        )
    await db.commit()


@router.put(
    "/reorder",
    status_code=status.HTTP_200_OK,
    summary="批量改 sort_order(单事务)",
)
async def reorder_watchlist(
    payload: WatchlistReorderIn,
    current_user: CurrentUserDep,
    db: DbDep,
) -> dict[str, int | str]:
    """按 item_ids 顺序重写 sort_order(0..N-1)。

    任一 item 不属于当前用户 / 不存在 → 全部回滚 + 404。
    """
    for index, item_id in enumerate(payload.item_ids):
        result = await db.execute(
            update(WatchlistItem)
            .where(
                WatchlistItem.id == item_id,
                WatchlistItem.user_id == current_user.id,
            )
            .values(sort_order=index)
            .returning(WatchlistItem.id),
        )
        if result.scalar_one_or_none() is None:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"自选股 {item_id} 不存在或无权限",
            )
    await db.commit()
    return {"status": "ok", "reordered": len(payload.item_ids)}
