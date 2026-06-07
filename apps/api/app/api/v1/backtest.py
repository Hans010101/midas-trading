"""研究室回测路由 · /api/v1/backtest · P1-4c.5 full-data(ADR 0038 · B 档报告 UI 取数)。

- GET  ""          · 列本人回测历史(created_at 倒序 · 走 ix_backtest_runs_user_created 索引)。
- GET  "/{run_id}" · 按 id 取单条 full-data(含 equity/trades/run_card · 仅本人 · 越权 404)。
- POST ""          · 发起一次回测(归属 current_user · 异步)· ★ orchestration 待产品负责人拍板后补。

🔴 红线:纯研究记录的只读展示 + 发起 —— 绝不下单 / 撮合 / 余额 / 真实交易。
   全部端点 authed-only(CurrentUserDep),按 current_user.id 过滤;取他人 run 返回 404(不是 403)。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.models.backtest_run import BacktestRun
from app.schemas.backtest import BacktestRunListItem, BacktestRunResponse

router = APIRouter(prefix="/backtest", tags=["backtest"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[BacktestRunListItem], summary="列本人回测历史(倒序)")
async def list_backtest_runs(
    current_user: CurrentUserDep,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[BacktestRunListItem]:
    """当前用户的回测历史 · created_at 倒序 · 精简项(不带 equity/trades 重数据)。"""
    stmt = (
        select(BacktestRun)
        .where(BacktestRun.user_id == current_user.id)
        .order_by(BacktestRun.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [BacktestRunListItem.model_validate(row) for row in rows]


@router.get(
    "/{run_id}",
    response_model=BacktestRunResponse,
    summary="按 id 取单条回测(full-data · 仅本人)",
)
async def get_backtest_run(
    run_id: int, current_user: CurrentUserDep, db: DbDep,
) -> BacktestRunResponse:
    """单条 full-data(含 metrics/equity/trades/run_card)· 越权防护:他人 run 视作不存在(404)。"""
    stmt = select(BacktestRun).where(
        BacktestRun.id == run_id,
        BacktestRun.user_id == current_user.id,
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="回测记录不存在",
        )
    return BacktestRunResponse.model_validate(run)
