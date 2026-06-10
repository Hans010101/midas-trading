"""回测服务层(块1)· api 编排:组装 config + 解析 artifacts。★ 绝不 import vibe。

两层解耦(vibe 只装在 midas-vibe 容器,api 容器没装 → api 端不能 import backtest.*):
  - api 编排(本模块):构造 config 契约 + 从 run_dir 解析结果。纯函数 / 只读文件。
  - vibe 容器执行(deploy/vibe/run_backtest_job.py):真正 import CryptoEngine +
    MidasCHLoader 走路径B 跑回测,把 artifacts 写到共享 run_dir。

🔴 红线:纯研究 · 绝不 import/调用 place_market_order 或虚拟下单引擎 · loader 只读 CH。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

import pandas as pd

from app.services.backtest.types import (
    BacktestMetrics,
    BacktestParams,
    BacktestResult,
    EquityPoint,
    Trade,
)

# vibe 回测 source 标签(路径B 纯标签 · 数据只走 MidasCHLoader,引擎不查 registry)
_SOURCE_LABEL = "ccxt"
_ENGINE = "daily"

# Midas period → Vibe interval(= loader interval 映射的逆)
_PERIOD_TO_INTERVAL: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "1d": "1D",
    "1w": "1W",
}

# crypto 7×24 年化基数 · 防御回退值(period 不在映射表时用 · P2-period 起按 period 映射)
CRYPTO_BARS_PER_YEAR = 365

# period → bars_per_year(crypto 7×24:1h=24×365=8760 · 1d=365 · 1w=52)。
# ★ P2-period 关键补丁:此前 config 不带 bars_per_year,vibe job 永远回退 365 → 1h 的
#   年化类指标(annual_return/sharpe/sortino/calmar/IR)会差 ~24× 量级(把每根小时 bar 当一天年化)。
#   分钟档(1m/5m/15m/30m)当前产品不放开,真要放开时在此补映射,缺省回退 365 是防御不是正确值。
_PERIOD_BARS_PER_YEAR: dict[str, int] = {
    "1h": 8760,
    "1d": 365,
    "1w": 52,
}

# metrics.csv 的 16 字段(顺序对齐 vibe calc_metrics);两个整型字段单列。
_METRIC_FIELDS: tuple[str, ...] = (
    "final_value",
    "total_return",
    "annual_return",
    "max_drawdown",
    "sharpe",
    "calmar",
    "sortino",
    "win_rate",
    "profit_loss_ratio",
    "profit_factor",
    "max_consecutive_loss",
    "avg_holding_days",
    "trade_count",
    "benchmark_return",
    "excess_return",
    "information_ratio",
)
_METRIC_INT_FIELDS: frozenset[str] = frozenset({"max_consecutive_loss", "trade_count"})


def to_vibe_code(symbol: str) -> str:
    """Midas/CH 符号 → vibe code(去斜杠/横杠 · 避引擎 ohlcv_{code}.csv 路径坑)。"""
    return symbol.strip().upper().replace("/", "").replace("-", "")


def build_backtest_config(params: BacktestParams) -> dict[str, object]:
    """组装 vibe 回测 config(块2 job 消费)· 纯函数无 IO。

    period 不支持 → ValueError(不静默给错周期)。
    """
    interval = _PERIOD_TO_INTERVAL.get(params.period)
    if interval is None:
        supported = sorted(_PERIOD_TO_INTERVAL)
        msg = f"backtest: 不支持的 period {params.period!r};支持={supported}"
        raise ValueError(msg)
    return {
        "codes": [to_vibe_code(params.symbol)],
        "start_date": params.start,
        "end_date": params.end,
        "source": _SOURCE_LABEL,
        "interval": interval,
        "engine": _ENGINE,
        "initial_cash": params.initial_cash,
        "leverage": params.leverage,
        # 确定性 SMA 交叉参数(块2 job 据此手搓 signal_engine)
        "sma_fast": params.sma_fast,
        "sma_slow": params.sma_slow,
        # 年化基数按 period 传给 vibe job(P2-period:1h=8760 · 1d=365;缺省防御回退 365)
        "bars_per_year": _PERIOD_BARS_PER_YEAR.get(params.period, CRYPTO_BARS_PER_YEAR),
    }


def _parse_metrics(run_dir: Path) -> BacktestMetrics:
    """读 artifacts/metrics.csv 单行 → 16 字段(缺文件/空/缺字段都明确 raise)。"""
    path = run_dir / "artifacts" / "metrics.csv"
    if not path.exists():
        msg = f"backtest: 缺 metrics.csv({path})"
        raise FileNotFoundError(msg)
    frame = pd.read_csv(path)
    if frame.empty:
        msg = f"backtest: metrics.csv 为空({path})"
        raise ValueError(msg)
    row = frame.iloc[0].to_dict()
    out: dict[str, float | int] = {}
    for key in _METRIC_FIELDS:
        if key not in row:
            msg = f"backtest: metrics.csv 缺字段 {key!r}"
            raise ValueError(msg)
        out[key] = int(row[key]) if key in _METRIC_INT_FIELDS else float(row[key])
    return cast(BacktestMetrics, out)


def _parse_equity(run_dir: Path) -> list[EquityPoint]:
    """读 artifacts/equity.csv → EquityPoint 列表(缺文件则空列表)。"""
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    points: list[EquityPoint] = []
    for _, r in frame.iterrows():
        points.append(
            EquityPoint(
                timestamp=str(r["timestamp"]),
                equity=float(r["equity"]),
                drawdown=float(r.get("drawdown", 0.0)),
                benchmark_equity=float(r.get("benchmark_equity", 0.0)),
                ret=float(r.get("ret", 0.0)),
                active_ret=float(r.get("active_ret", 0.0)),
            ),
        )
    return points


def _parse_trades(run_dir: Path) -> list[Trade]:
    """读 artifacts/trades.csv → Trade 列表(缺文件则空列表)。"""
    path = run_dir / "artifacts" / "trades.csv"
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    trades: list[Trade] = []
    for _, r in frame.iterrows():
        trades.append(
            Trade(
                timestamp=str(r["timestamp"]),
                code=str(r["code"]),
                side=str(r["side"]),
                price=float(r["price"]),
                qty=float(r["qty"]),
                reason=str(r["reason"]),
                pnl=float(r["pnl"]),
                holding_days=float(r["holding_days"]),
                return_pct=float(r["return_pct"]),
            ),
        )
    return trades


def _parse_run_card(run_dir: Path) -> dict[str, object]:
    """读 run_card.json(缺则空 dict)。"""
    path = run_dir / "run_card.json"
    if not path.exists():
        return {}
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def parse_artifacts(run_dir: Path, params: BacktestParams) -> BacktestResult:
    """从 run_dir/artifacts 解析回测结果(读 CSV + run_card.json)。

    metrics.csv 必须存在且非空(否则 raise)· equity/trades 缺则空列表。
    """
    return BacktestResult(
        params=asdict(params),
        metrics=_parse_metrics(run_dir),
        equity=_parse_equity(run_dir),
        trades=_parse_trades(run_dir),
        run_card=_parse_run_card(run_dir),
    )
