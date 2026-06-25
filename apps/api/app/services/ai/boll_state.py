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

# ★推送声明:精简后声明由转换行「· 仅供参考」承载;STRUCTURE_DISCLAIMER 兼容保留(仍是合规声明之一)。
PUSH_DISCLAIMER = "· 仅供参考"          # 方案B 转换行末缀(精简后的主声明)
STRUCTURE_DISCLAIMER = "· 结构描述非建议"  # 兼容保留 · 仍被门禁认可为合规声明
# 详情页深链(Telegram Markdown [text](url))· 做T 三种消息统一:单卡 render_card / 合并列表
# build_transition_digest / 全景 boll_digest(后者另有同值常量)· 点 SYMBOL 一一对应进详情。
DETAIL_URL = "https://midastrade.asia/crypto-preview"
# ★合规声明集(裸短语 · 匹配不依赖「· 」前缀)· 文案含其一 = 有声明;★完全无 → 门禁一票否决(不改松)。
_COMPLIANT_DISCLAIMERS: tuple[str, ...] = ("仅供参考", "结构描述非建议")

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

_ZONE_LABEL = {
    "over_upper": "破上轨", "upper": "近上轨", "mid": "近中轨",
    "lower": "近下轨", "over_lower": "破下轨", "middle": "中间",
}


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
    # ★越界优先判定:%B>1 收盘超上轨(破上轨)· %B<0 收盘跌穿下轨(破下轨)· 同改 TG 影子 + 接口
    if pct_b > 1.0:
        return "over_upper"
    if pct_b > _PCTB_HIGH:
        return "upper"
    if pct_b < 0.0:
        return "over_lower"
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


def render_card(symbol: str, snap: BollSnapshot, transition_from: str | None = None) -> str:
    """单 symbol 结构卡(定稿方案B · ★不含整批末尾免责、不含买卖词)。

    方案B 多行格式:倾向 / 状态 / 通道位置 / 现价 / 轨道 /(有转换时)状态转换行末缀「· 仅供参考」。
    transition_from 给「转换前状态中文口诀」时,追加「状态转换:X → Y · 仅供参考」(免责缀在转换行,
    不占独立行);为 None(无转换)则省略该行。整批末尾的唯一免责由 build_session_message 统一加。
    """
    lines = [
        # ★SYMBOL 超链接进详情(与全景 / 合并列表一致 · 一一对应)· 只给标的加链接,其余文案不动
        f"[{symbol}]({DETAIL_URL}?symbol={symbol})｜结构倾向:{snap.bias}",
        f"状态:{_STATE_LABEL[snap.state]}",
        f"通道位置:{_ZONE_LABEL[snap.zone]}(%B={snap.pct_b:.2f})",
        f"现价 {snap.close:g}",
        f"轨道 上 {snap.upper:g} / 中 {snap.mid:g} / 下 {snap.lower:g}",
    ]
    if transition_from:
        lines.append(f"状态转换:{transition_from} → {_STATE_LABEL[snap.state]} · 仅供参考")
    return "\n".join(lines)


def push_strength(snap: BollSnapshot) -> float:
    """推送排序「信号强度」= |%B − 0.5|(离中轨越远 = 破轨越显著 = 越优先推)· 纯描述派生,无方向判断。

    %B=0.5 在中轨 → 强度 0;近轨 ±0.3;破轨(%B>1 或 <0)→ >0.5。转换多时按此降序取最强若干。
    """
    return abs(snap.pct_b - 0.5)


def select_for_push(
    cands: list[tuple[str, BollSnapshot, str]],
    *,
    batch_max: int,
    daily_remaining: int,
) -> list[tuple[str, BollSnapshot, str]]:
    """频率控制纯逻辑(可单测 · 无 Redis/IO):按信号强度降序,先批量上限、再每日剩余上限,取最强子集。

    cands 是【已过冷却 + 涨跌榜】前置筛选的候选(Redis 留 worker)· 每项 (symbol, snap, 转换前口诀)。
    返回「本轮该影子推送」子集(≤ min(batch_max, daily_remaining))· daily_remaining≤0 → 空。
    """
    ranked = sorted(cands, key=lambda c: push_strength(c[1]), reverse=True)
    return ranked[: max(0, min(batch_max, daily_remaining))]


def state_label(state: BollState) -> str:
    """状态枚举 → 中文口诀(供快照 / 做T接口复用 _STATE_LABEL)。"""
    return _STATE_LABEL[state]


def to_snapshot_row(
    symbol: str,
    snap: BollSnapshot,
    *,
    change_pct_24h: float | None,
    funding_rate: float | None,
    transition: bool,
    prev_state: str | None,
) -> dict[str, Any]:
    """单币结构快照行(做T A-1/A-2 列表数据源 · ★复用 snap 不重算 · 纯描述、无买卖措辞)。

    键与 schemas.crypto.BollScanItem 字段一一对应(extra=forbid)。transition_from 仅在
    发生状态转换且有合法 prev 时给中文口诀,否则 None。bandwidth/zone_label 全是布林衍生
    (零成本);funding_rate 由调用方批量读 CH 传入(无数据 None)。
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
        "zone_label": _ZONE_LABEL[snap.zone],  # 通道位置中文(破上轨/近上轨/…)· 后端单源
        "bandwidth": snap.bandwidth,  # (upper-lower)/mid · 布林衍生零成本
        "close": snap.close,
        "mid": snap.mid,
        "upper": snap.upper,
        "lower": snap.lower,
        "change_pct_24h": change_pct_24h,
        "funding_rate": funding_rate,  # 批量读 crypto_funding_rate · 无数据 None
        "transition": transition,
        "transition_from": transition_from,
    }


def validate_shadow_push(text: str) -> str:
    """★影子推送文案门禁(比 validate_advisory 更严):

    ① 复用 scrub_marketing 清营销话术 + has_marketing_violation 兜底拒;
    ② ★必须含至少一个【合规声明】(仅供参考 / 结构描述非建议)· 完全无声明 → 一票否决(门禁不失效);
    ③ 正文(剔除合规声明短语后)出现买卖祈使/预测黑名单词 → 一票否决。
    通过则返回清洗后的文案;否则 raise ValueError(绝不放行)。

    ★精简说明:末尾不再强制固定免责行,声明改由转换行「· 仅供参考」承载 —— 门禁从「末尾匹配固定串」
    放宽为「含合规声明之一」,但【无任何声明仍拒】(②),拦截作用不变,绝不松到「无声明也能过」。
    """
    raw = text.rstrip()
    # ① 营销违规(稳赚/保证收益…)→ 一票否决(★原文检测 · 推送绝不静默改写)
    if has_marketing_violation(raw):
        msg = "推送文案含营销违规话术"
        raise ValueError(msg)
    # ② ★必须含合规声明 · 否则一票否决(无声明文案绝不放行 —— 门禁的拦截本质)
    if not any(d in raw for d in _COMPLIANT_DISCLAIMERS):
        msg = "推送文案缺合规免责声明(需含 仅供参考 / 结构描述非建议)"
        raise ValueError(msg)
    # ③ 买卖祈使/预测黑名单 → 一票否决(★剔除合规声明短语后再检,免「结构描述非建议」的「建议」误伤)
    body = raw
    for disc in _COMPLIANT_DISCLAIMERS:
        body = body.replace(disc, "")
    for word in _FORBIDDEN_PUSH_WORDS:
        if word in body:
            msg = f"推送正文含买卖祈使/预测词:{word}"
            raise ValueError(msg)
    return scrub_marketing(raw)  # 复用 scrub_marketing 兜底归一(此处已无违规 · 幂等 no-op)


def build_session_message(cards: list[str]) -> str:
    """合并多张结构卡为【一条】会话消息(定稿方案B)· 头 + 分隔线分卡 · 经门禁后返回。

    方案B:头「📊 布林做T信号 · 15m永续」→ 每卡前后用分隔线。★声明精简:不再加末尾重复的
    STRUCTURE_DISCLAIMER 行,声明由各卡转换行末缀的「· 仅供参考」承载;validate_shadow_push 仍强制
    校验「含合规声明」(无声明则拒)。推送卡均带转换行(候选都是转换),故必含「仅供参考」过门禁。
    """
    header = "📊 布林做T信号 · 15m永续"
    sep = "————————"
    parts = [header]
    for card in cards:
        parts.append(sep)
        parts.append(card)
    parts.append(sep)  # 末尾分隔线收尾(★不再加重复声明行 · 声明在转换行)
    return validate_shadow_push("\n".join(parts))


def build_transition_digest(pushed: list[tuple[str, BollSnapshot, str]]) -> str:
    """≥2 个转换合并为【一条】简版列表(做T M2-3b · 体系2)· 经门禁后返回。

    每行:emoji(方向 📈/📉/➖ · ★不用 🟢🔴 红绿)+ SYMBOL 超链接 + 转{倾向} + 结构转换路径
    (transition_from → 当前状态)+ %B 通道位置。单个转换不走这里(走方案B 完整卡)。
    倾向只偏多/偏空/中性 · 转换方向用结构语言(状态口诀)· 无买卖词 · 末尾「· 仅供参考」过门禁。
    pushed 每项 = (symbol, snap, transition_from 中文口诀)· 由 worker 在 M2-1 筛选后传入(不重算)。
    """
    lines = [f"📊 布林做T · 转换提醒({len(pushed)}个)"]
    for sym, snap, transition_from in pushed:
        emoji = "📈" if snap.bias == "偏多" else "📉" if snap.bias == "偏空" else "➖"
        url = f"{DETAIL_URL}?symbol={sym}"
        lines.append(
            f"{emoji} [{sym}]({url})｜转{snap.bias} · "
            f"{transition_from} → {_STATE_LABEL[snap.state]} · %B={snap.pct_b:.2f}",
        )
    lines.append(PUSH_DISCLAIMER)  # 末尾唯一「· 仅供参考」
    return validate_shadow_push("\n".join(lines))
