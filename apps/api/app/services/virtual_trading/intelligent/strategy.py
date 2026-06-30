"""智能交易 · 策略引擎(打分共振)· 智能交易 PR-3 · 🔴纯函数决策计算 · ★还不下单(下单 = PR-4)。

★PR-0 §1·B 权重共振:布林 bias(boll 快照)+ MACD/MA/RSI/KDJ/extreme 方向分(intelligent 快照)各 ×权重
→ 加权求和 → |得分| > 3.0 开多/开空 → ATR 止损(2×)/止盈(4×·2:1 盈亏比)。
★纯函数:输入两快照【该币】数据 + 标记价 → 输出决策(StrategyDecision)· 不依赖 DB/Redis · 可纯单测。
★参数 hardcode 常量(Hans 认可 · 全可调 · 将来要调再加 Redis 配置 · 像托管 tp_pct)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ★策略参数(Hans 认可 · 全可调 · 先 hardcode)─────────────────────────
WEIGHTS: dict[str, float] = {
    "boll": 2.0, "macd": 1.5, "ma": 1.5, "rsi": 1.0, "kdj": 1.0, "extreme": 1.0,
}  # 满分 8.0(全偏多)/ −8.0(全偏空)
OPEN_THRESHOLD = 3.0   # |加权得分| > 3.0 → 开仓(= 3.0 不开 · 需严格大于)
ATR_STOP_MULT = 2.0    # 止损 = entry ∓ 2×ATR
ATR_TP_MULT = 4.0      # 止盈 = entry ± 4×ATR(2:1 盈亏比)


@dataclass(frozen=True)
class StrategyDecision:
    symbol: str
    action: str                    # open_long / open_short / hold
    score: float                   # 加权得分(−8.0 ~ +8.0)
    entry_price: float             # 决策时标记价(PR-4 实际开仓价以 route 为准)
    stop_loss: float | None        # ATR 止损价(hold 或 ATR=0 → None)
    take_profit: float | None      # ATR 止盈价(2:1)
    contributions: dict[str, int]  # 各指标方向分(共振明细 · PR-4 记录 + PR-6 看板)


def _bias_to_dir(bias: str | None) -> int:
    """布林 bias → 方向分(偏多 +1 / 偏空 −1 / 中性·缺 0)。"""
    if bias == "偏多":
        return 1
    if bias == "偏空":
        return -1
    return 0


def decide(
    symbol: str,
    boll_item: dict[str, Any] | None,
    signal_item: dict[str, Any],
    price: float,
    *,
    threshold: float = OPEN_THRESHOLD,
    weights: dict[str, float] | None = None,
    atr_stop_mult: float = ATR_STOP_MULT,
    atr_tp_mult: float = ATR_TP_MULT,
) -> StrategyDecision:
    """单币决策(★纯函数 · 策略参数入参 · 不读 Redis · 可测)。

    boll_item = boll 快照该币(可 None=布林缺)· signal_item = intelligent 快照该币 · price = 标记价。
    ★threshold/weights/atr_*_mult 默认 module 常量(向后兼容)· 调用层读 Redis 传入 → 即时生效。
    """
    w = weights if weights is not None else WEIGHTS
    contributions: dict[str, int] = {
        "boll": _bias_to_dir(boll_item.get("bias") if boll_item else None),
        "macd": int(signal_item.get("macd_dir", 0) or 0),
        "ma": int(signal_item.get("ma_dir", 0) or 0),
        "rsi": int(signal_item.get("rsi_dir", 0) or 0),
        "kdj": int(signal_item.get("kdj_dir", 0) or 0),
        "extreme": int(signal_item.get("extreme_dir", 0) or 0),
    }
    score = round(sum(contributions[k] * w.get(k, 0.0) for k in contributions), 2)
    atr = float(signal_item.get("atr", 0) or 0)

    if score > threshold:
        action = "open_long"
        stop = round(price - atr_stop_mult * atr, 8) if atr > 0 else None
        tp = round(price + atr_tp_mult * atr, 8) if atr > 0 else None
    elif score < -threshold:
        action = "open_short"
        stop = round(price + atr_stop_mult * atr, 8) if atr > 0 else None
        tp = round(price - atr_tp_mult * atr, 8) if atr > 0 else None
    else:
        action, stop, tp = "hold", None, None

    return StrategyDecision(
        symbol=symbol, action=action, score=score, entry_price=price,
        stop_loss=stop, take_profit=tp, contributions=contributions,
    )


def build_decisions(
    boll_items: list[dict[str, Any]],
    signal_items: list[dict[str, Any]],
    *,
    threshold: float = OPEN_THRESHOLD,
    weights: dict[str, float] | None = None,
    atr_stop_mult: float = ATR_STOP_MULT,
    atr_tp_mult: float = ATR_TP_MULT,
) -> list[StrategyDecision]:
    """批量决策 · boll 按 symbol 索引取 price(close)· 遍历 signal_items。

    ★策略参数透传给 decide(默认常量)· 无 boll 该币(无 close)→ 跳过(布林最高权重·price 取 close)。
    """
    boll_map = {str(x["symbol"]): x for x in boll_items if x.get("symbol")}
    out: list[StrategyDecision] = []
    for sig in signal_items:
        sym = str(sig.get("symbol") or "")
        boll = boll_map.get(sym)
        if not sym or boll is None or not boll.get("close"):
            continue
        out.append(decide(
            sym, boll, sig, float(boll["close"]),
            threshold=threshold, weights=weights,
            atr_stop_mult=atr_stop_mult, atr_tp_mult=atr_tp_mult,
        ))
    return out


def open_decisions(
    decisions: list[StrategyDecision],
    *,
    allow_long: bool = True,
    allow_short: bool = True,
) -> list[StrategyDecision]:
    """只取要开仓的(action ≠ hold)· PR-4 开仓编排用。

    ★PR-8 方向过滤(只过滤不改方向):allow_long/allow_short 默认 True(=现状·不滤)。
    禁某方向 → 滤掉该方向的 decision · ★绝不改 decide 算出的 action/side/score 本身。
    """
    out: list[StrategyDecision] = []
    for d in decisions:
        if d.action == "hold":
            continue
        if d.action == "open_long" and not allow_long:
            continue
        if d.action == "open_short" and not allow_short:
            continue
        out.append(d)
    return out
