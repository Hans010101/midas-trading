"""布林带做T「6 口诀」状态机(纯计算 · 影子模式 M1)。

★对齐基座:布林算法完全复用 strategy_signals._boll_series(中轨 MA20 · 上下轨 ±2.0×样本std(n−1)),
不另算一套。本模块只在其上派生【三线斜率 / 带宽收放 / %B 位置】→ 映射 6 个离散结构状态 +
结构倾向(偏多/偏空/中性 · ★描述现状,非预测、非建议)。

🔴 红线:
- 全是「结构描述」· 状态/倾向措辞绝不出现 建议/买入/卖出/目标价/止损 等祈使或预测词。
- 推送文案统一经 validate_shadow_push 门禁:买卖黑名单一票否决 + 末尾恰好一行免责。
- 本模块纯计算 · 不读写任何外部(CH/Redis/TG 由调用方 worker 处理)。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from app.schemas.market import Kline
from app.services.ai.strategy_signals import _BOLL_K, _BOLL_PERIOD, _boll_series
from app.services.ai.validator import has_marketing_violation, scrub_marketing

# ── 派生维度阈值(常量便于调)──────────────────────────────────────────────
_SLOPE_LOOKBACK = 4          # 中轨斜率 / 带宽收放回看根数
_SLOPE_EPS = 0.003           # 中轨 4 根累计变动 > ±0.3% 判齐上/齐跌,否则走平
_BW_EPS = 0.10               # 带宽 4 根累计变动 > ±10% 判开口/收口,否则平稳
_PCTB_HIGH = 0.8             # %B > 0.8 近上轨
_PCTB_LOW = 0.2              # %B < 0.2 近下轨
_PCTB_MID_LO, _PCTB_MID_HI = 0.4, 0.6  # 近中轨区间

# classify 所需最少根数:布林预热 period + 斜率/带宽回看
_MIN_BARS = _BOLL_PERIOD + _SLOPE_LOOKBACK

# ★推送免责(整批末尾唯一一行)· 锁死红线
STRUCTURE_DISCLAIMER = "· 结构描述非建议"

# ★买卖祈使 / 预测词黑名单(推送正文出现任一 → validate_shadow_push 一票否决)
_FORBIDDEN_PUSH_WORDS: tuple[str, ...] = (
    "建议", "买入", "卖出", "抄底", "逃顶", "目标价", "止损", "止盈",
    "做多", "做空", "加仓", "减仓", "建仓", "清仓", "梭哈", "满仓",
    "buy", "sell", "long", "short",
)


class BollState(enum.Enum):
    """6 口诀离散结构状态。"""

    TREND_UP = "trend_up"        # 三线齐上 · 上升结构
    TREND_DOWN = "trend_down"    # 三线齐跌 · 下降结构
    RANGE = "range"              # 三线走平 + 带宽平稳 · 震荡结构
    BREAKOUT_UP = "breakout_up"  # 带宽开口 + 向上
    SQUEEZE = "squeeze"          # 带宽持续收口 · 方向未明
    BREAKDOWN = "breakdown"      # 带宽开口 + 向下


_STATE_LABEL: dict[BollState, str] = {
    BollState.TREND_UP: "三线齐上·上升结构",
    BollState.TREND_DOWN: "三线齐跌·下降结构",
    BollState.RANGE: "三线走平·震荡结构",
    BollState.BREAKOUT_UP: "带宽开口·向上",
    BollState.SQUEEZE: "带宽收口·方向未明",
    BollState.BREAKDOWN: "带宽开口·向下",
}

_ZONE_LABEL = {"upper": "近上轨", "mid": "近中轨", "lower": "近下轨", "middle": "中间"}


@dataclass(frozen=True)
class BollSnapshot:
    """某 symbol 最新一根的布林结构快照(纯描述)。"""

    state: BollState
    bias: str           # 偏多 / 偏空 / 中性
    pct_b: float        # (close-lower)/(upper-lower)
    bandwidth: float    # (upper-lower)/mid
    zone: str           # upper / mid / lower / middle
    close: float
    mid: float
    upper: float
    lower: float


def _zone(pct_b: float) -> str:
    if pct_b > _PCTB_HIGH:
        return "upper"
    if pct_b < _PCTB_LOW:
        return "lower"
    if _PCTB_MID_LO <= pct_b <= _PCTB_MID_HI:
        return "mid"
    return "middle"


def _bias(state: BollState, pct_b: float) -> str:
    """结构倾向(描述现状,非预测)。"""
    if state in (BollState.TREND_UP, BollState.BREAKOUT_UP):
        return "偏多"
    if state in (BollState.TREND_DOWN, BollState.BREAKDOWN):
        return "偏空"
    if state is BollState.SQUEEZE:
        return "中性"
    # RANGE:近下轨=下轨低吸结构(偏多)· 近上轨=上轨高抛结构(偏空)· 中间=中性
    if pct_b < _PCTB_LOW:
        return "偏多"
    if pct_b > _PCTB_HIGH:
        return "偏空"
    return "中性"


def classify(klines: list[Kline]) -> BollSnapshot | None:
    """最近 K 线 → 布林结构快照。不足预热根数返回 None。"""
    if len(klines) < _MIN_BARS:
        return None
    closes = [float(k.close) for k in klines]
    boll = _boll_series(closes, _BOLL_PERIOD, _BOLL_K)
    cur, prev = boll[-1], boll[-1 - _SLOPE_LOOKBACK]
    if cur is None or prev is None:
        return None
    mid, upper, lower = cur
    pmid, pupper, plower = prev
    close = closes[-1]
    width = upper - lower
    if width <= 0 or mid <= 0:
        return None

    pct_b = (close - lower) / width
    bandwidth = width / mid
    # 三线斜率(以中轨为代表)· 带宽收放(now vs lookback 前)
    slope = (mid - pmid) / pmid if pmid else 0.0
    pbw = (pupper - plower) / pmid if pmid else 0.0
    bw_change = (bandwidth - pbw) / pbw if pbw else 0.0

    slope_up = slope > _SLOPE_EPS
    slope_down = slope < -_SLOPE_EPS

    if bw_change <= -_BW_EPS:                     # 收口 → 方向未明
        state = BollState.SQUEEZE
    elif bw_change >= _BW_EPS:                     # 开口 → 按方向
        if slope_down or pct_b < _PCTB_LOW:
            state = BollState.BREAKDOWN
        elif slope_up or pct_b > _PCTB_HIGH:
            state = BollState.BREAKOUT_UP
        else:
            state = BollState.RANGE               # 开口但方向未定 → 暂归震荡
    elif slope_up:                                # 带宽平稳 + 齐上
        state = BollState.TREND_UP
    elif slope_down:                              # 带宽平稳 + 齐跌
        state = BollState.TREND_DOWN
    else:                                         # 走平 + 带宽平稳
        state = BollState.RANGE

    return BollSnapshot(
        state=state, bias=_bias(state, pct_b), pct_b=round(pct_b, 3),
        bandwidth=round(bandwidth, 4), zone=_zone(pct_b),
        close=close, mid=round(mid, 6), upper=round(upper, 6), lower=round(lower, 6),
    )


def render_card(symbol: str, snap: BollSnapshot) -> str:
    """单 symbol 结构卡(★不含免责、不含买卖词 · 免责由 build_session_message 末尾统一加)。"""
    return (
        f"【{symbol}】{_STATE_LABEL[snap.state]} · 结构倾向:{snap.bias}\n"
        f"  %B={snap.pct_b:.2f}({_ZONE_LABEL[snap.zone]}) · "
        f"现价 {snap.close:g} | 中轨 {snap.mid:g} | 上 {snap.upper:g} / 下 {snap.lower:g}"
    )


def state_label(state: BollState) -> str:
    """状态枚举 → 中文口诀(供快照 / 做T接口复用 _STATE_LABEL)。"""
    return _STATE_LABEL[state]


def to_snapshot_row(
    symbol: str,
    snap: BollSnapshot,
    *,
    change_pct_24h: float | None,
    transition: bool,
    prev_state: str | None,
) -> dict[str, Any]:
    """单币结构快照行(做T A-1 列表数据源 · ★复用 snap 不重算 · 纯描述、无买卖措辞)。

    键与 schemas.crypto.BollScanItem 字段一一对应(extra=forbid)。transition_from 仅在
    发生状态转换且有合法 prev 时给中文口诀,否则 None。
    """
    transition_from: str | None = None
    if transition and prev_state:
        try:
            transition_from = _STATE_LABEL[BollState(prev_state)]
        except ValueError:
            transition_from = None
    return {
        "symbol": symbol,
        "state": snap.state.value,
        "state_label": _STATE_LABEL[snap.state],
        "bias": snap.bias,
        "pct_b": snap.pct_b,
        "close": snap.close,
        "mid": snap.mid,
        "upper": snap.upper,
        "lower": snap.lower,
        "change_pct_24h": change_pct_24h,
        "transition": transition,
        "transition_from": transition_from,
    }


def validate_shadow_push(text: str) -> str:
    """★影子推送文案门禁(M1 新建 · 比现有 validate_advisory 更严):

    ① 复用 scrub_marketing 清营销话术 + has_marketing_violation 兜底拒;
    ② 正文(末尾免责行之外)出现买卖祈使/预测黑名单词 → 一票否决(raise);
    ③ 末尾必须恰好一行 STRUCTURE_DISCLAIMER。
    通过则返回清洗后的文案;否则 raise ValueError(绝不放行)。
    """
    raw = text.rstrip()
    # ① 营销违规(稳赚/保证收益…)→ 一票否决(★原文检测 · 推送绝不静默改写)
    if has_marketing_violation(raw):
        msg = "推送文案含营销违规话术"
        raise ValueError(msg)
    # ② 末尾必须恰好一行免责
    if not raw.endswith(STRUCTURE_DISCLAIMER):
        msg = "推送文案末尾必须是免责行"
        raise ValueError(msg)
    body = raw[: -len(STRUCTURE_DISCLAIMER)]
    if STRUCTURE_DISCLAIMER in body:
        msg = "免责行只能出现一次(末尾)"
        raise ValueError(msg)
    # ③ 买卖祈使/预测黑名单 → 一票否决(★检正文 · 免责行「非建议」不误伤)
    for word in _FORBIDDEN_PUSH_WORDS:
        if word in body:
            msg = f"推送正文含买卖祈使/预测词:{word}"
            raise ValueError(msg)
    return scrub_marketing(raw)  # 复用 scrub_marketing 兜底归一(此处已无违规 · 幂等 no-op)


def build_session_message(cards: list[str]) -> str:
    """合并多张结构卡为【一条】会话级消息 + 末尾唯一免责 · 经 validate_shadow_push 门禁后返回。"""
    header = "📊 布林结构扫描(15m · 加密永续)"
    parts = [header, *cards, STRUCTURE_DISCLAIMER]
    return validate_shadow_push("\n".join(parts))
