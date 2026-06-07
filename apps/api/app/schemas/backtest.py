"""研究室回测 API Pydantic 契约 · P1-4c.5 full-data(ADR 0038 · B 档报告 UI 取数自渲染)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:回测是【纯研究记录】的只读展示 + 发起 —— 绝不下单 / 撮合 / 余额 / 真实交易。
   全部端点 authed-only,按 current_user.id 过滤(越权取他人 run 返回 404)。
═══════════════════════════════════════════════════════════════════════════

- BacktestCreateRequest  · POST 请求体(照 service.BacktestParams · 确认报告 C8)。
- BacktestCreateResponse · POST 响应(run id + status · 供前端拿 id 轮询)。
- BacktestRunListItem    · GET 列表项(精简 · 不带重数据 equity/trades)。
- BacktestRunResponse    · GET 单条(full-data · 含 equity/trades/run_card)。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 与 service._PERIOD_TO_INTERVAL 的 key 对齐(确认报告 C8)· 不支持的 period 在此层 422。
BacktestPeriod = Literal["1m", "5m", "15m", "30m", "1h", "1d", "1w"]


class BacktestCreateRequest(BaseModel):
    """POST /api/v1/backtest 请求体 · 字段照 BacktestParams(symbol/start/end 必填,余可选带默认)。"""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=64)
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")  # YYYY-MM-DD
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")  # YYYY-MM-DD
    market: Literal["crypto"] = "crypto"  # 当前仅 crypto(模型注释 · 确认报告 C4)
    period: BacktestPeriod = "1d"
    sma_fast: int = Field(default=5, ge=1, le=400)
    sma_slow: int = Field(default=20, ge=1, le=400)
    initial_cash: float = Field(default=1_000_000.0, gt=0)
    leverage: float = Field(default=1.0, gt=0, le=125)


class BacktestCreateResponse(BaseModel):
    """POST 响应 · 返回 run id + status(pending)供前端轮询 GET /{id}。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    status: str


class BacktestRunListItem(BaseModel):
    """GET /api/v1/backtest 列表项 · 精简(不带重数据 equity/trades · 避免列表 payload 过大)。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: int
    symbol: str
    market: str
    period: str
    start_date: str
    end_date: str
    status: str
    created_at: datetime


class BacktestRunResponse(BaseModel):
    """GET /api/v1/backtest/{id} 单条 · full-data(含 equity/trades/run_card · B 档报告渲染)。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: int
    symbol: str
    market: str
    period: str
    start_date: str
    end_date: str
    params_json: dict[str, object]
    status: str
    metrics_json: dict[str, object] | None = None
    equity_json: list[dict[str, object]] | None = None
    trades_json: list[dict[str, object]] | None = None
    run_card_json: dict[str, object] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
