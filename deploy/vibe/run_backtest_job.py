#!/usr/bin/env python3
"""run_backtest_job · midas-vibe 容器内回测执行入口(路径B · 产品化 ch_smoke)。

★ 仅在 midas-vibe 容器内运行:import vibe 的 backtest.* + 运行时挂载的 midas_ch_loader。
  本文件 import vibe 包,而 api 容器没装 vibe → 故放 deploy/vibe/(天然不被 api 的
  ruff/mypy 扫,test.yml working-directory=apps/api)。

职责:接回测参数(JSON)→ 路径B(CryptoEngine + MidasCHLoader + 确定性 SMA 交叉)→
  写 artifacts 到 run_dir → 打印结构化 JSON(status/run_id/run_dir/metrics)→ 退出码语义。

🔴 红线:纯研究 · 只读 CH(MidasCHLoader 只 SELECT)· 不 import registry/_get_loader/
  resolve_loader(路径B 无外部源 fallback)· 绝不连 place_market_order / 虚拟下单引擎。

入参(三选一,优先级 argv > env):
  argv[1] = config JSON 字符串,或指向 config.json 的路径;或 env VIBE_BACKTEST_CONFIG(JSON)。
config 字段(= apps/api 的 app.services.backtest.build_backtest_config 产出):
  codes[] / start_date / end_date / source / interval / engine / initial_cash / leverage /
  sma_fast / sma_slow;可选 run_dir / run_id / bars_per_year。

退出码:0 = 成功;非 0 = 失败(打印 status=error 的 JSON)。
注:vibe 引擎 run_backtest 内部遇「无数据/无有效信号」会自行打印 error JSON 并 sys.exit(1)
    (SystemExit 不被本兜底捕获,直接以其退出码+其 JSON 退出);本兜底负责其余异常
    (CH 连接失败 / loader 报错 / import 失败等)→ 统一转 status=error JSON + 退出 1。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path

# 运行时挂载的 midas_ch_loader 与本脚本同目录(/work)· 与 P1-4a 验证布局一致。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_DEFAULT_BARS_PER_YEAR = 365  # crypto 7x24 → 日线按 365 年化


def _load_config(argv: list[str]) -> dict:
    """从 argv[1](JSON 串或文件路径)或 env VIBE_BACKTEST_CONFIG 读 config。"""
    raw: str | None = None
    if len(argv) > 1 and argv[1].strip():
        arg = argv[1].strip()
        candidate = Path(arg)
        raw = candidate.read_text(encoding="utf-8") if candidate.is_file() else arg
    elif os.environ.get("VIBE_BACKTEST_CONFIG"):
        raw = os.environ["VIBE_BACKTEST_CONFIG"]
    if not raw:
        raise SystemExit(
            "run_backtest_job: 缺 config(argv[1] 传 JSON 串/路径,或 env VIBE_BACKTEST_CONFIG)",
        )
    cfg = json.loads(raw)
    if not isinstance(cfg, dict):
        raise SystemExit("run_backtest_job: config 必须是 JSON object")
    return cfg


def _build_sma_signal_engine(sma_fast: int, sma_slow: int):
    """确定性 SMA 交叉信号:fast SMA > slow SMA → 做多(1.0)否则空仓(0.0)。零 LLM。

    契约(vibe engines/base.py:353):generate(data_map) -> {code: pd.Series}。
    """

    class _SmaCrossSignalEngine:
        def generate(self, data_map):
            out = {}
            for code, frame in data_map.items():
                fast = frame["close"].rolling(sma_fast, min_periods=1).mean()
                slow = frame["close"].rolling(sma_slow, min_periods=1).mean()
                out[code] = (fast > slow).astype(float)  # index == frame.index
            return out

    return _SmaCrossSignalEngine()


def run_one(config: dict) -> dict:
    """路径B 跑一次回测,返回结构化结果 dict(CLI main 与 vibe Celery task 共用)。

    永远返回 {status: "ok"|"error", run_id, run_dir, artifacts_dir, metrics?/error?}
    —— 不 print、不 sys.exit、不 raise(顶层兜底转 error dict),便于经 Celery result 传回主 worker。
    """
    run_dir = Path(config.get("run_dir") or tempfile.mkdtemp(prefix="vibe_bt_"))
    run_id = str(config.get("run_id") or run_dir.name or uuid.uuid4().hex[:12])
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 路径B:显式 import 引擎 + 显式 loader · 绝不碰 registry/_get_loader/resolve_loader。
        from backtest.engines.crypto import CryptoEngine

        from midas_ch_loader import MidasCHLoader

        sma_fast = int(config.get("sma_fast", 5))
        sma_slow = int(config.get("sma_slow", 20))
        bars_per_year = int(config.get("bars_per_year", _DEFAULT_BARS_PER_YEAR))

        engine = CryptoEngine(config)
        loader = MidasCHLoader()
        signal_engine = _build_sma_signal_engine(sma_fast, sma_slow)

        metrics = engine.run_backtest(
            config, loader, signal_engine, run_dir=run_dir, bars_per_year=bars_per_year,
        )
        scalar = {k: v for k, v in metrics.items() if not isinstance(v, dict)}
        return {
            "status": "ok",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "artifacts_dir": str(run_dir / "artifacts"),
            "metrics": scalar,
        }
    except Exception as exc:  # noqa: BLE001 — 顶层兜底:任何失败转 error dict(不 raise · 便于 Celery result)
        return {
            "status": "error",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }


def main() -> int:
    """CLI 入口(保持 P1-4a 实测的 argv/env 行为):读 config → run_one → print JSON → 退出码。"""
    cfg = _load_config(sys.argv)
    result = run_one(cfg)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
