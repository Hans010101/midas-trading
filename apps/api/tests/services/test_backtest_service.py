"""块1 回测服务层单测 · 纯函数 + artifacts 解析(CH-free / vibe-free · CI 可跑)。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.services.backtest.service import (
    build_backtest_config,
    parse_artifacts,
    to_vibe_code,
)
from app.services.backtest.types import BacktestParams


def test_to_vibe_code_strips_separators() -> None:
    assert to_vibe_code("BTC/USDT") == "BTCUSDT"
    assert to_vibe_code("btc-usdt") == "BTCUSDT"
    assert to_vibe_code("BTCUSDT") == "BTCUSDT"


def test_build_backtest_config_crypto_1d() -> None:
    params = BacktestParams(symbol="BTC/USDT", start="2025-01-17", end="2026-05-31")
    cfg = build_backtest_config(params)
    assert cfg["codes"] == ["BTCUSDT"]  # 去斜杠避引擎写盘坑
    assert cfg["interval"] == "1D"  # 1d → 1D
    assert cfg["source"] == "ccxt"  # 路径B 纯标签
    assert cfg["engine"] == "daily"
    assert cfg["sma_fast"] == 5
    assert cfg["sma_slow"] == 20
    assert cfg["start_date"] == "2025-01-17"
    assert cfg["end_date"] == "2026-05-31"


def test_build_backtest_config_bad_period() -> None:
    params = BacktestParams(
        symbol="BTCUSDT", start="2025-01-01", end="2025-02-01", period="3d",
    )
    with pytest.raises(ValueError, match="不支持的 period"):
        build_backtest_config(params)


def _write_fixture_artifacts(run_dir: Path) -> None:
    art = run_dir / "artifacts"
    art.mkdir(parents=True)
    metrics = {
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
    }
    pd.DataFrame([metrics]).to_csv(art / "metrics.csv", index=False)
    pd.DataFrame(
        {
            "timestamp": ["2025-01-17", "2025-01-18"],
            "ret": [0.0, 0.01],
            "equity": [1_000_000.0, 1_010_000.0],
            "drawdown": [0.0, 0.0],
            "benchmark_equity": [1_000_000.0, 1_005_000.0],
            "active_ret": [0.0, 0.005],
        },
    ).to_csv(art / "equity.csv", index=False)
    pd.DataFrame(
        {
            "timestamp": ["2025-01-18"],
            "code": ["BTCUSDT"],
            "side": ["buy"],
            "price": [95_000.0],
            "qty": [0.1],
            "reason": ["entry"],
            "pnl": [0.0],
            "holding_days": [0.0],
            "return_pct": [0.0],
        },
    ).to_csv(art / "trades.csv", index=False)
    (run_dir / "run_card.json").write_text(
        json.dumps({"reproducibility": {"config_hash": "abc"}, "data_sources": ["ccxt"]}),
        encoding="utf-8",
    )


def test_parse_artifacts_full(tmp_path: Path) -> None:
    _write_fixture_artifacts(tmp_path)
    params = BacktestParams(symbol="BTC/USDT", start="2025-01-17", end="2026-05-31")
    result = parse_artifacts(tmp_path, params)

    # metrics:16 字段齐 + 整型字段是 int
    assert len(result["metrics"]) == 16
    assert result["metrics"]["trade_count"] == 12
    assert isinstance(result["metrics"]["trade_count"], int)
    assert isinstance(result["metrics"]["max_consecutive_loss"], int)
    assert result["metrics"]["total_return"] == pytest.approx(0.1)

    # equity / trades
    assert len(result["equity"]) == 2
    assert result["equity"][1]["equity"] == pytest.approx(1_010_000.0)
    assert len(result["trades"]) == 1
    assert result["trades"][0]["code"] == "BTCUSDT"

    # run_card + params 回填
    assert result["run_card"]["data_sources"] == ["ccxt"]
    assert result["params"]["symbol"] == "BTC/USDT"


def test_parse_artifacts_missing_metrics(tmp_path: Path) -> None:
    params = BacktestParams(symbol="BTCUSDT", start="2025-01-01", end="2025-02-01")
    with pytest.raises(FileNotFoundError, match="metrics.csv"):
        parse_artifacts(tmp_path, params)
