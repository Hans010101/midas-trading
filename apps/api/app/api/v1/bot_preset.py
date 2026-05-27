"""Bot 下单后台预设路由 · /api/v1/bot-preset · 0026 G5。

- GET  · 返回当前用户预设;无行 → 默认值(load_preset · 与 G4 常量一致)。
- PUT  · upsert 当前用户预设(本期 perp_margin_mode 固定 isolated)。

🔴 user_id 只取自登录用户(CurrentUserDep),绝不从请求体取。预设只影响 bot 下单的
默认参数,下单本身全程虚拟引擎。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.models.bot_order_preset import BotOrderPreset
from app.schemas.bot_preset import BotPresetResponse, BotPresetUpdate
from app.services.bot.order import load_preset

router = APIRouter(prefix="/bot-preset", tags=["bot-preset"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=BotPresetResponse, summary="bot 下单后台预设(无则返回默认)")
async def get_bot_preset(
    current_user: CurrentUserDep, db: DbDep,
) -> BotPresetResponse:
    p = await load_preset(db, current_user.id)
    return BotPresetResponse(
        perp_leverage=p.perp_leverage,
        perp_notional_usdt=p.perp_notional_usdt,
        perp_margin_mode=p.perp_margin_mode,
        spot_notional_cny=p.spot_notional_cny,
        spot_notional_usd=p.spot_notional_usd,
    )


@router.put("", response_model=BotPresetResponse, summary="保存 bot 下单后台预设(upsert)")
async def put_bot_preset(
    payload: BotPresetUpdate, current_user: CurrentUserDep, db: DbDep,
) -> BotPresetResponse:
    row = await db.get(BotOrderPreset, current_user.id)
    if row is None:
        row = BotOrderPreset(user_id=current_user.id)
        db.add(row)
    row.perp_leverage = payload.perp_leverage
    row.perp_notional_usdt = payload.perp_notional_usdt
    row.perp_margin_mode = "isolated"  # 本期固定逐仓(防误设全仓)
    row.spot_notional_cny = payload.spot_notional_cny
    row.spot_notional_usd = payload.spot_notional_usd
    await db.commit()
    return BotPresetResponse(
        perp_leverage=row.perp_leverage,
        perp_notional_usdt=row.perp_notional_usdt,
        perp_margin_mode=row.perp_margin_mode,
        spot_notional_cny=row.spot_notional_cny,
        spot_notional_usd=row.spot_notional_usd,
    )
