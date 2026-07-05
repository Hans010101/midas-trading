"""告警规则路由 · /api/v1/alert-rules/* · 0025 G2b。

用户增删改查自己的告警规则 + 列出可选指标清单(供网页 G5 / bot G3 渲染)。
指标合法性 / 市场适用 / 是否需 symbol / DP6 数量上限 在此校验。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, RequestLangDep
from app.core.database import get_db
from app.models.alert_rule import AlertRule
from app.schemas.alert_rule import (
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
    IndicatorMeta,
    to_response,
)
from app.services.alerts.engine import MAX_RULES_PER_USER
from app.services.alerts.recommended import apply_recommended_rules
from app.services.alerts.registry import REGISTRY, get_indicator
from app.services.i18n import translate


class ApplyRecommendedResult(BaseModel):
    created: int
    skipped: int

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/indicators",
    response_model=list[IndicatorMeta],
    summary="可选告警指标清单(供前端 / bot 渲染)",
)
async def list_indicators() -> list[IndicatorMeta]:
    return [
        IndicatorMeta(
            key=d.key, label=d.label, category=d.category, markets=list(d.markets),
            requires_symbol=d.requires_symbol, needs_timeframe=d.needs_timeframe,
            unit=d.unit,
        )
        for d in REGISTRY.values()
    ]


@router.get("", response_model=list[AlertRuleResponse], summary="我的告警规则")
async def list_alert_rules(
    current_user: CurrentUserDep, db: DbDep,
) -> list[AlertRuleResponse]:
    rows = await db.execute(
        select(AlertRule)
        .where(AlertRule.user_id == current_user.id)
        .order_by(AlertRule.created_at.asc()),
    )
    return [to_response(r) for r in rows.scalars().all()]


@router.post(
    "",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增告警规则",
)
async def create_alert_rule(
    payload: AlertRuleCreate, current_user: CurrentUserDep, db: DbDep, lang: RequestLangDep,
) -> AlertRuleResponse:
    # 1. 指标合法 + 市场适用
    indicator = get_indicator(payload.indicator)
    if indicator is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("alert_rule.unknown_indicator", lang, indicator=payload.indicator),
        )
    if payload.market not in indicator.markets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate(
                "alert_rule.indicator_market_unsupported",
                lang,
                indicator=payload.indicator,
                market=payload.market,
            ),
        )

    # 2. symbol 要求:per-symbol 指标必传;市场级指标忽略传入的 symbol
    symbol = payload.symbol.strip() if payload.symbol else None
    if indicator.requires_symbol and not symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate(
                "alert_rule.indicator_requires_symbol", lang, indicator=payload.indicator,
            ),
        )
    if not indicator.requires_symbol:
        symbol = None  # 市场级指标:忽略 symbol

    # 3. DP6 数量护栏
    count = await db.scalar(
        select(func.count())
        .select_from(AlertRule)
        .where(AlertRule.user_id == current_user.id),
    )
    if (count or 0) >= MAX_RULES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("alert_rule.max_rules_reached", lang, max_rules=MAX_RULES_PER_USER),
        )

    rule = AlertRule(
        user_id=current_user.id,
        market=payload.market,
        symbol=symbol,
        indicator=payload.indicator,
        operator=payload.operator,
        threshold=payload.threshold,
        timeframe=payload.timeframe if indicator.needs_timeframe else None,
        cooldown_sec=payload.cooldown_sec,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return to_response(rule)


@router.post(
    "/apply-recommended",
    response_model=ApplyRecommendedResult,
    summary="一键应用推荐告警规则(跳过已存在 / 超上限)",
)
async def apply_recommended(
    current_user: CurrentUserDep, db: DbDep,
) -> ApplyRecommendedResult:
    # 🔴 user_id 取自登录用户,绝不从请求体取
    created, skipped = await apply_recommended_rules(db, current_user.id)
    return ApplyRecommendedResult(created=created, skipped=skipped)


@router.patch(
    "/{rule_id}", response_model=AlertRuleResponse, summary="修改告警规则(部分)",
)
async def update_alert_rule(
    rule_id: int, payload: AlertRuleUpdate, current_user: CurrentUserDep, db: DbDep,
    lang: RequestLangDep,
) -> AlertRuleResponse:
    rule = await db.scalar(
        select(AlertRule).where(
            AlertRule.id == rule_id, AlertRule.user_id == current_user.id,
        ),
    )
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("alert_rule.not_found_or_forbidden", lang),
        )
    if payload.operator is not None:
        rule.operator = payload.operator
    if payload.threshold is not None:
        rule.threshold = payload.threshold
    if payload.timeframe is not None:
        rule.timeframe = payload.timeframe
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    if payload.cooldown_sec is not None:
        rule.cooldown_sec = payload.cooldown_sec
    await db.commit()
    await db.refresh(rule)
    return to_response(rule)


@router.delete(
    "/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除告警规则",
)
async def delete_alert_rule(
    rule_id: int, current_user: CurrentUserDep, db: DbDep, lang: RequestLangDep,
) -> None:
    result = await db.execute(
        delete(AlertRule)
        .where(AlertRule.id == rule_id, AlertRule.user_id == current_user.id)
        .returning(AlertRule.id),
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("alert_rule.not_found_or_forbidden", lang),
        )
    await db.commit()
