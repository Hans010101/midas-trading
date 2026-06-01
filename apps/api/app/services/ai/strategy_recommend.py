"""策略推荐适配层 · 形态A 单元2(ADR 0037 §4 · 拍板③ 纯规则推荐)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 纯函数确定性映射(类比 actionable.py)· 零 LLM 成本 · 不改 AI 分析管线。
   - 只读:复用 indicators.py 的 compute_* 算当前行情状态(读,不改 compute_* 契约)。
   - 只推荐「适合哪个策略」· 不下单 / 不执行 / 不打实时上游。
═══════════════════════════════════════════════════════════════════════════

推荐逻辑(ADR 0037 §4 · 优先级:趋势 > RSI 极值 > 贴轨 > 兜底):
- 趋势市(trend_5d=up/down)              → ma_cross(均线金叉/死叉跟踪趋势)
- 震荡市 + RSI 偏极值(≤35 / ≥65)        → rsi_reversal(超卖反弹/超买回落)
- 震荡市 + 价格贴布林轨(%B ≤0.2 / ≥0.8)  → boll_reversion(均值回归)
- 震荡市无明显极值                         → ma_cross 兜底(最经典 · 观察趋势启动)

纯逻辑 _pick(trend, rsi, pctb) 与取数 recommend_strategy(klines) 拆开,_pick 易单测各分支。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.strategy import StrategyRecommendation
from app.services.ai import indicators as ind

if TYPE_CHECKING:
    from app.schemas.market import Kline

# ===== 阈值(MVP 固定 · 与单元1 策略参数呼应)=====
_MIN_BARS = 20                  # 不足 BOLL/MA20 预热 → 兜底
_RSI_OVERSOLD_ZONE = 35.0       # RSI ≤ 此值视为偏超卖(比策略触发线 30 略宽 · 推荐用)
_RSI_OVERBOUGHT_ZONE = 65.0     # RSI ≥ 此值视为偏超买
_PCTB_LOW = 0.2                 # %B ≤ 此值视为贴近下轨
_PCTB_HIGH = 0.8                # %B ≥ 此值视为贴近上轨


def _pick(
    trend: str, rsi: float, pctb: float | None,
) -> StrategyRecommendation:
    """纯逻辑:由当前 (趋势, RSI, 布林 %B) 推荐策略 · 确定性 · 可单测各分支。

    pctb = (close - lower) / (upper - lower);布林带退化(width=0)时传 None。
    """
    # 1) 趋势市 → 均线金叉/死叉
    if trend == "up":
        return StrategyRecommendation(
            strategy="ma_cross", reason="近 5 日上行趋势 · 适合均线金叉跟踪趋势",
        )
    if trend == "down":
        return StrategyRecommendation(
            strategy="ma_cross", reason="近 5 日下行趋势 · 适合均线死叉跟踪趋势",
        )

    # 2) 震荡市 + RSI 偏极值 → RSI 反弹
    if rsi <= _RSI_OVERSOLD_ZONE:
        return StrategyRecommendation(
            strategy="rsi_reversal",
            reason=f"震荡市 + RSI {rsi:.0f} 偏超卖 · 适合 RSI 超卖反弹策略",
        )
    if rsi >= _RSI_OVERBOUGHT_ZONE:
        return StrategyRecommendation(
            strategy="rsi_reversal",
            reason=f"震荡市 + RSI {rsi:.0f} 偏超买 · 适合 RSI 超买回落策略",
        )

    # 3) 震荡市 + 价格贴布林轨 → 均值回归
    if pctb is not None:
        if pctb <= _PCTB_LOW:
            return StrategyRecommendation(
                strategy="boll_reversion",
                reason="震荡市 + 价格贴近布林下轨 · 适合均值回归(博反弹)",
            )
        if pctb >= _PCTB_HIGH:
            return StrategyRecommendation(
                strategy="boll_reversion",
                reason="震荡市 + 价格贴近布林上轨 · 适合均值回归(博回落)",
            )

    # 4) 兜底:震荡无明显极值 → 均线金叉(最经典)
    return StrategyRecommendation(
        strategy="ma_cross", reason="震荡市无明显极值 · 默认均线金叉观察趋势启动",
    )


def recommend_strategy(klines: list[Kline]) -> StrategyRecommendation:
    """给一段 K 线,推荐当前适合哪个策略 · 纯函数 · 复用 compute_*(读不改)。

    数据不足(< 20 根)→ 兜底 ma_cross(避免在未预热指标上瞎推荐)。
    """
    if len(klines) < _MIN_BARS:
        return StrategyRecommendation(
            strategy="ma_cross", reason="K 线数据不足 · 默认均线金叉策略",
        )

    trend = ind.compute_trend_5d(klines)        # up / down / sideways
    rsi = ind.compute_rsi(klines).get(14, 50.0)
    boll = ind.compute_boll(klines)
    last_close = float(klines[-1].close)

    width = boll["upper"] - boll["lower"]
    pctb = (last_close - boll["lower"]) / width if width > 0 else None

    return _pick(trend, rsi, pctb)


__all__ = ["recommend_strategy"]
