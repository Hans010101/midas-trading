"""回测服务结果结构(块1)· api 编排层契约 · 绝不 import vibe。

跨层契约:
  - BacktestParams:回测入参(symbol/market/period/start/end/SMA 窗口/资金)。
  - BacktestMetrics:vibe calc_metrics 的 16 个标量指标(metrics.csv 单行)。
  - EquityPoint / Trade:equity.csv / trades.csv 的行结构。
  - BacktestResult:组装后的完整结果(落库 metrics_json + 前端用)。

🔴 红线:纯研究结果结构,绝不参与撮合 / 下单 / 余额任何计算。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True, slots=True)
class BacktestParams:
    """回测入参 · 确定性 SMA 交叉策略(LLM 接入是后续 P2,不在此)。"""

    symbol: str
    start: str  # YYYY-MM-DD
    end: str  # YYYY-MM-DD
    market: str = "crypto"
    period: str = "1d"
    sma_fast: int = 5
    sma_slow: int = 20
    initial_cash: float = 1_000_000.0
    leverage: float = 1.0


class BacktestMetrics(TypedDict):
    """vibe calc_metrics 的 16 个标量指标(metrics.csv 列 · 全 float/int)。"""

    final_value: float
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe: float
    calmar: float
    sortino: float
    win_rate: float
    profit_loss_ratio: float
    profit_factor: float
    max_consecutive_loss: int
    avg_holding_days: float
    trade_count: int
    benchmark_return: float
    excess_return: float
    information_ratio: float


class EquityPoint(TypedDict):
    """equity.csv 一行(index=timestamp + 5 列)。"""

    timestamp: str
    equity: float
    drawdown: float
    benchmark_equity: float
    ret: float
    active_ret: float


class Trade(TypedDict):
    """trades.csv 一行(9 列)。"""

    timestamp: str
    code: str
    side: str
    price: float
    qty: float
    reason: str
    pnl: float
    holding_days: float
    return_pct: float


class BacktestResult(TypedDict):
    """组装后的完整回测结果(落库 + 前端用)。"""

    params: dict[str, object]  # BacktestParams 的 asdict
    metrics: BacktestMetrics
    equity: list[EquityPoint]
    trades: list[Trade]
    run_card: dict[str, object]  # run_card.json 原样(reproducibility/data_sources 等)
