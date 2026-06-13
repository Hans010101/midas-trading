"""研究室回测路由 · /api/v1/backtest · P1-4c.5 full-data(ADR 0038 · B 档报告 UI 取数)。

- POST ""          · 发起一次回测(归属 current_user · 异步)· 建 pending 行 → enqueue worker。
- GET  ""          · 列本人回测历史(created_at 倒序 · 走 ix_backtest_runs_user_created 索引)。
- GET  "/{run_id}" · 按 id 取单条 full-data(含 equity/trades/run_card · 仅本人 · 越权 404)。

🔴 红线:纯研究记录的只读展示 + 发起 —— 绝不下单 / 撮合 / 余额 / 真实交易。
   全部端点 authed-only(CurrentUserDep),按 current_user.id 过滤;取他人 run 返回 404(不是 403)。
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.models.backtest_run import BacktestRun
from app.models.user import User
from app.schemas.backtest import (
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestRunListItem,
    BacktestRunResponse,
)
from app.services.backtest.persistence import create_pending_run
from app.services.backtest.types import BacktestParams
from app.services.membership import consume_quota, require_quota

router = APIRouter(prefix="/backtest", tags=["backtest"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── enqueue 到 worker(照抄 services/notifications/emit.py:lazy Celery client + send_task by name)──
# ★ api 不 import worker · 只按任务名 send_task · broker 与主 worker 共用 CELERY_BROKER_URL。
_celery_client: Any | None = None


def _get_celery_client() -> Any:
    """Lazy 创建 Celery 客户端 · 仅作 broker 发任务的轻量客户端(同 emit.py)。"""
    global _celery_client  # noqa: PLW0603
    if _celery_client is None:
        from celery import Celery  # noqa: PLC0415

        broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
        _celery_client = Celery("midas-api", broker=broker)
    return _celery_client


def enqueue_run_backtest(params: dict[str, object], user_id: str, backtest_run_id: int) -> None:
    """触发 worker 跑回测(by name)· 复用 API 已建的 pending 行 id(避免双 pending · P1-4c.5)。"""
    _get_celery_client().send_task(
        "tasks.backtest.run_backtest",
        args=[params, user_id],
        kwargs={"backtest_run_id": backtest_run_id},
    )


@router.post("", response_model=BacktestCreateResponse, summary="发起一次回测(归属本人 · 异步)")
async def create_backtest_run(
    payload: BacktestCreateRequest,
    # 会员刀1:额度闸(429 · 只查不扣)· 扣减在 pending 行创建成功 commit 后
    current_user: Annotated[User, Depends(require_quota("backtest"))],
    db: DbDep,
) -> BacktestCreateResponse:
    """建 pending 行(归属本人)→ commit 拿 id → enqueue worker(传 id · worker 复用不再自建)。

    返回 {id, status:"pending"};结果由 vibe-worker 跑完经 persist_outcome 回填(前端轮询 GET /{id})。
    """
    params = BacktestParams(
        symbol=payload.symbol,
        start=payload.start,
        end=payload.end,
        market=payload.market,
        period=payload.period,
        sma_fast=payload.sma_fast,
        sma_slow=payload.sma_slow,
        initial_cash=payload.initial_cash,
        leverage=payload.leverage,
    )
    run = await create_pending_run(db, params, user_id=current_user.id)
    # 先 commit 让 pending 行落地,再 enqueue(对齐 worker 的 commit→send 顺序,避免链路抢在 commit
    #   前读不到行)· enqueue 失败则该 pending 由 beat scan_stale_pending 兜底扫成 error。
    await db.commit()
    # 创建成功才扣(create_pending_run/commit 抛错则不扣 · 调研 P3 拍板)
    await consume_quota(current_user.id, "backtest")
    enqueue_run_backtest(asdict(params), str(current_user.id), run.id)
    return BacktestCreateResponse(id=run.id, status=run.status)


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
        # created_at 平局(同事务 now() 恒定)→ 显式 id tie-break(铁律 · 同 conditional 修法)
        .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
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
