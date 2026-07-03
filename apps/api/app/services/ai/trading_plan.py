"""交易计划参考 · 三价位【纯规则】算价(入场区间 / 止损失效价 / 双目标 / 盈亏比)。

★ 原则:价位数字 100% 规则计算,绝不让 LLM 凭空生成(与 B1/B2 同属缠论/指标规则家族)。
   plan_note(为什么这么定)才由 AI 写,见 agents/plan_note.py。

算价素材(均来自 TechnicalSnapshot · 见 workflow.data_prepare 注入):
  当前价 last_close · 布林上中下轨 boll · ATR(止损缓冲)· 缠论最近中枢上下沿 zhongshu_high/low。
方向:score≥20→long · score≤-20→short · 其余→neutral(三价位全 None · 前端优雅降级)。
止损:第一版 = 纯结构失效价 ∓ 0.5×ATR,【不做爆仓校验】(无杠杆上下文 · 留待仓位/杠杆建议阶段)。
目标:R 倍数(1.5R / 3R)为骨架,target1 命中附近结构位时吸附到真实阻力/支撑(更可读)。
保证:long → entry_low<entry_high≤现价、stop<entry_low、target1>entry、target2>target1;short 对调。
"""

from __future__ import annotations

from app.schemas.ai_decision import PlanDirection, TradingPlan


def _round_price(p: float) -> float:
    """按价格量级选小数位(BTC 6万→2位 · 山寨 0.08→5位)。"""
    a = abs(p)
    if a >= 1000:
        return round(p, 2)
    if a >= 1:
        return round(p, 3)
    if a >= 0.01:
        return round(p, 5)
    return round(p, 7)


def _direction_of(score: int) -> PlanDirection:
    if score >= 20:
        return "long"
    if score <= -20:
        return "short"
    return "neutral"


def compute_trading_plan(
    *,
    score: int,
    last_close: float,
    boll: dict[str, float],
    atr: float,
    zhongshu_high: float | None,
    zhongshu_low: float | None,
) -> TradingPlan:
    """按方向规则算出三价位 + 盈亏比(plan_note 留空 · 由调用方填 AI/模板)。"""
    direction = _direction_of(score)
    price = last_close
    if direction == "neutral" or price <= 0:
        # 中性 / 异常价 → 不给三价位(前端优雅降级)
        return TradingPlan(direction="neutral")

    # ATR 兜底:数据不足时用现价 2% 当波幅,避免除零 / 退化
    eff_atr = atr if atr and atr > 0 else price * 0.02
    band = 0.3 * eff_atr
    boll_up = boll.get("upper")
    boll_mid = boll.get("mid")
    boll_lo = boll.get("lower")

    if direction == "long":
        # 入场:顺势【回撤带】· 参考位取「现价下方最近的支撑」(中枢下沿 > 布林中轨),否则现价-ATR
        below = [v for v in (zhongshu_low, boll_mid) if v is not None and v < price]
        ref = max(below) if below else price - eff_atr
        entry_high = min(ref + band, price)        # ★不追现价
        entry_low = ref - band
        if entry_low >= entry_high:                # 退化保护
            entry_high = price - band
            entry_low = price - 3 * band
        entry = (entry_low + entry_high) / 2
        # 失效价:结构地板(中枢下沿/布林下轨/入场下沿 取最低)- 0.5 ATR
        floor = min(v for v in (zhongshu_low, boll_lo, entry_low) if v is not None)
        stop = floor - 0.5 * eff_atr
        risk = entry - stop                        # >0(stop<entry_low<entry)
        target1 = entry + 1.5 * risk
        target2 = entry + 3.0 * risk
        # 吸附:上方真实阻力落在 (1R, 2.5R) 区间内 → target1 用它(更贴结构)
        res = [v for v in (zhongshu_high, boll_up) if v is not None and v > entry]
        if res:
            nearest = min(res)
            if entry + 1.0 * risk <= nearest <= entry + 2.5 * risk:
                target1 = nearest
    else:  # short — 镜像
        above = [v for v in (zhongshu_high, boll_mid) if v is not None and v > price]
        ref = min(above) if above else price + eff_atr
        entry_low = max(ref - band, price)         # ★不追现价(空头等反弹)
        entry_high = ref + band
        if entry_high <= entry_low:
            entry_low = price + band
            entry_high = price + 3 * band
        entry = (entry_low + entry_high) / 2
        ceil_ = max(v for v in (zhongshu_high, boll_up, entry_high) if v is not None)
        stop = ceil_ + 0.5 * eff_atr
        risk = stop - entry                        # >0
        target1 = entry - 1.5 * risk
        target2 = entry - 3.0 * risk
        sup = [v for v in (zhongshu_low, boll_lo) if v is not None and v < entry]
        if sup:
            nearest = max(sup)
            if entry - 2.5 * risk <= nearest <= entry - 1.0 * risk:
                target1 = nearest

    risk_reward = abs((target1 - entry) / (entry - stop)) if entry != stop else None

    return TradingPlan(
        direction=direction,
        entry_low=_round_price(entry_low),
        entry_high=_round_price(entry_high),
        stop=_round_price(stop),
        target1=_round_price(target1),
        target2=_round_price(target2),
        risk_reward=round(risk_reward, 2) if risk_reward is not None else None,
    )


def template_note(plan: TradingPlan) -> str:
    """规则模板兜底解释(mock 模式 / LLM 失败时用 · 价位感知 · 陈述句不含祈使)。"""
    if plan.direction == "neutral" or plan.entry_low is None:
        return "当前多空信号中性,结构未给出明确顺势入场位,倾向观望等待方向选择。"
    side = "做多" if plan.direction == "long" else "做空"
    verb = "回撤至" if plan.direction == "long" else "反弹至"
    invalid = "跌破" if plan.direction == "long" else "站上"
    return (
        f"{side}计划:不追现价,等{verb} {plan.entry_low}–{plan.entry_high} 区间;"
        f"{invalid} {plan.stop} 则本结构失效;目标看向 {plan.target1} / {plan.target2}"
        f"(盈亏比约 {plan.risk_reward})。以上为规则测算的参考区间,非操作指令。"
    )


def template_note_en(plan: TradingPlan) -> str:
    """英文规则模板兜底(i18n Phase4 刀2)· en 用户在 mock / LLM 失败 / 串台降级时用。

    ★为什么要 en 版:zh template_note 是中文,en 用户回退到它就【中文漏给英文用户】=破红线。
    价位数字与 zh 版一字不差(纯规则算)· 陈述句不含祈使 · 免责由 ensure_advisory_disclaimer_en 兜底。
    """
    if plan.direction == "neutral" or plan.entry_low is None:
        return (
            "Long/short signals are neutral; the structure offers no clear "
            "trend-following entry, so staying on the sidelines is the read."
        )
    side = "Long" if plan.direction == "long" else "Short"
    verb = "a pullback to" if plan.direction == "long" else "a bounce to"
    invalid = "breaks below" if plan.direction == "long" else "reclaims"
    return (
        f"{side} plan: rather than chasing price, the structure is framed around {verb} the "
        f"{plan.entry_low}–{plan.entry_high} zone; it is invalidated if price {invalid} "
        f"{plan.stop}; targets sit at {plan.target1} / {plan.target2} "
        f"(risk-reward about {plan.risk_reward}). These are rule-computed reference levels, "
        "not a trading instruction."
    )


__all__ = ["compute_trading_plan", "template_note", "template_note_en"]
