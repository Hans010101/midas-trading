"""X 推文合规门禁(机器可验 · 公开金融内容 · ★比 TG 做T门禁更严)。

参考 boll_state.validate_shadow_push 范式(黑名单 + 一票否决 + 声明检查),X 在其上【加预测词黑名单】。
★营销违规检测对【原始 AI 输出】做(不对清洗后做)—— 学做T教训(0002 / boll_state):
  检测放在 scrub 之前,否则清洗后再检会漏掉本应一票否决的原文。
任一维度命中 → 该推文【否决】(passed=False)+ 记录原因,不进候选。全过 → passed=True。

★为什么不拉黑裸「涨/跌/涨跌」:推文要如实报 24h 涨跌幅(事实陈述,过去/现状),
  拉黑裸涨跌会把每条合规推文都误杀。改为只拦【预测性复合词】(暴涨/将涨/看涨/涨到…)
  + 未来时态标记 —— 拦"预测未来",放行"描述现状"。这是门禁不沦为废物的关键设计。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.ai.validator import has_marketing_violation

# ① 买卖引导黑名单(超集 boll_state._FORBIDDEN_PUSH_WORDS · X 再加运营常见诱导词)
_ACTION_WORDS: tuple[str, ...] = (
    "建议", "买入", "卖出", "买进", "卖掉", "抄底", "逃顶", "目标价", "目标位",
    "止损", "止盈", "加仓", "减仓", "建仓", "清仓", "梭哈", "满仓",
    "重仓", "上车", "布局", "吸纳", "可关注", "入场", "进场", "离场", "埋伏", "潜伏",
    "buy", "sell", "long", "short",
)
# ★做空/做多 默认拦(引导:建议做空/现在做空/做空机会),仅【陈述市场状态】白名单放行(剥掉后无残留即过)·
#   空头/多头 本就不拦(空头情绪/多头动能 天然过)· 只需处理含「做空/做多」的状态短语。
_HEDGE_STATE_ALLOW: tuple[str, ...] = (
    "做空情绪", "做空仓位", "做空力量", "做空动能", "做空盘",
    "做多情绪", "做多仓位", "做多力量", "做多动能", "做多盘",
)

# ② ★预测未来走势黑名单(X 专属严控)· 只拦【预测性复合词 / 未来时态】· 不含裸"涨/跌"(见 docstring)
#   ★「突破/破位」不放进裸词表(陈述句「无突破/未突破/突破信号」是事实状态,不该拦)·
#     改由下方 _PREDICTION_RES 正则只拦【未来/方向语境】的突破(即将突破/将突破/突破在即…)。
_PREDICTION_WORDS: tuple[str, ...] = (
    "暴涨", "暴跌", "大涨", "大跌", "将涨", "将跌", "会涨", "会跌", "要涨", "要跌",
    "看涨", "看跌", "续涨", "续跌", "补涨", "涨到", "跌到", "上看", "下看",
    "拉升", "冲高", "冲顶", "探底", "启动", "翻倍", "新高", "新低",
    "即将", "将要", "将会", "有望", "料将", "预计", "后市", "下一步", "未来", "接下来",
)
# ★涨至/跌至 默认拦(预测/目标:将跌至/有望涨至),仅【已发生/当前】白名单放行(剥掉后无残留即过)。
_PRICE_REACHED_ALLOW: tuple[str, ...] = (
    "已跌至", "已涨至", "回落至", "回升至", "运行至",
    "现跌至", "现涨至", "下探至", "上探至", "回踩至",
)

# ②b ★突破/破位【预测性】语境正则(陈述「无突破/未突破/突破信号」放行 · 只拦未来/在即/可期):
#    未来标记 + 突破/破位(即将突破/将破位/有望突破…),或 突破/破位 + 在即/可期(突破在即…)。
_PREDICTION_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(即将|将要|将会|将|有望|预计|料将|快要|很快|马上|或将|势必|会)(突破|破位)"),
    re.compile(r"(突破|破位)(在即|可期)"),
)

# ③ 收益承诺(has_marketing_violation 覆盖稳赚/保证收益;这里补 X 常见诱导)
_PROFIT_WORDS: tuple[str, ...] = (
    "翻倍", "稳赚", "保本", "收益率", "回报率", "躺赚", "财富自由", "一夜暴富", "百倍", "十倍",
)

# ④ 合规声明(★必须含其一,否则否决 —— 同 boll_state 门禁本质:无声明绝不放行)
_DISCLAIMERS: tuple[str, ...] = (
    "仅供参考", "不构成投资建议", "非投资建议", "风险自担", "自行决策",
)

_MAX_LEN = 700  # X 推文软上限(中文 · 防超长 · 任务定 280-500 区间,留余量到 700 才否决)


@dataclass(frozen=True)
class TweetGateResult:
    """门禁结果 · passed=False 时 reasons 列全部否决原因(便于审计哪条踩线)。"""

    passed: bool
    reasons: tuple[str, ...]


def _hits(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if w in text]


def validate_tweet(text: str) -> TweetGateResult:
    """X 推文合规门禁 · ★对【原始文本】检测(不清洗)· 一票否决 · 收集全部原因。

    六维:① 营销违规(对原文)② 买卖引导 ③ 预测未来 ④ 收益承诺 ⑤ 缺免责声明 ⑥ 超长。
    任一命中 → passed=False。全过 → passed=True。
    """
    raw = (text or "").strip()
    reasons: list[str] = []

    if not raw:
        return TweetGateResult(passed=False, reasons=("空文本",))

    # ★① 营销违规 + ② 声明存在性 → 对【原始文本】检测(学做T:营销不对 scrub 后检测,否则漏判)
    if has_marketing_violation(raw):
        reasons.append("营销违规话术(稳赚/保证收益/无风险等)")
    if not any(d in raw for d in _DISCLAIMERS):
        reasons.append("缺免责声明(需含 仅供参考 / 不构成投资建议)")

    # ★买卖/预测/收益词 → 对【剥掉合规声明短语后的 body】检测:否则免责语「不构成投资建议」里的
    #   「建议」会被买卖黑名单误杀(同 boll_state 范式 · 子串误判防线)。
    body = raw
    for disc in _DISCLAIMERS:
        body = body.replace(disc, "")
    if hits := _hits(body, _ACTION_WORDS):
        reasons.append(f"买卖引导词:{'/'.join(hits)}")
    pred = _hits(body, _PREDICTION_WORDS)
    pred += [m.group(0) for rgx in _PREDICTION_RES if (m := rgx.search(body))]  # 突破/破位 预测语境
    if pred:
        reasons.append(f"预测未来走势词:{'/'.join(pred)}")

    # ★做空/做多:剥陈述白名单(做空情绪/做空动能…)后仍残留裸词 → 引导(建议做空/做空机会)→ 拦
    hedge_body = body
    for ph in _HEDGE_STATE_ALLOW:
        hedge_body = hedge_body.replace(ph, "")
    if hits := _hits(hedge_body, ("做空", "做多")):
        reasons.append(f"买卖引导词(做空/做多·非陈述):{'/'.join(hits)}")
    # ★涨至/跌至:剥掉已发生白名单(已跌至/回落至…)后仍残留裸 涨至/跌至 → 预测/目标(将跌至/跌至XX)→ 拦
    price_body = body
    for ph in _PRICE_REACHED_ALLOW:
        price_body = price_body.replace(ph, "")
    if hits := _hits(price_body, ("涨至", "跌至")):
        reasons.append(f"预测未来走势词(涨至/跌至·非陈述):{'/'.join(hits)}")

    if hits := _hits(body, _PROFIT_WORDS):
        reasons.append(f"收益承诺词:{'/'.join(hits)}")
    if len(raw) > _MAX_LEN:
        reasons.append(f"过长({len(raw)} 字 · 超 {_MAX_LEN})")

    return TweetGateResult(passed=not reasons, reasons=tuple(reasons))
