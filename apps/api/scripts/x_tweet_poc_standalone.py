"""X 推文真 DeepSeek 验证 · ★自包含版(不依赖 app.services.x_marketing,可在生产 api 容器直接跑)。

x_marketing 模块只在分支、没进生产容器(跑 main)→ 原 x_tweet_poc.py import 报 ModuleNotFound。
本脚本把【门禁 / prompt / 形态数据】全内联(= 分支 x_marketing 逻辑逐字拷贝),只 import 容器 main 有的
ai.llm(ainvoke/is_mock_mode · 真 DeepSeek)+ ai.validator(has_marketing_violation)→ 真生成 + 真门禁,
★不往容器塞模块、跑完即净、不碰 main/部署。运行命令见任务回复(git show → docker cp → exec)。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from redis import asyncio as aioredis

from app.services.ai.llm import ainvoke, is_mock_mode
from app.services.ai.validator import has_marketing_violation

# ════════ 门禁(内联 · = x_marketing/compliance.py validate_tweet)════════
_ACTION_WORDS: tuple[str, ...] = (
    "建议", "买入", "卖出", "买进", "卖掉", "抄底", "逃顶", "目标价", "目标位",
    "止损", "止盈", "加仓", "减仓", "建仓", "清仓", "梭哈", "满仓",
    "重仓", "上车", "布局", "吸纳", "可关注", "入场", "进场", "离场", "埋伏", "潜伏",
    "buy", "sell", "long", "short",
)
_HEDGE_STATE_ALLOW: tuple[str, ...] = (
    "做空情绪", "做空仓位", "做空力量", "做空动能", "做空盘",
    "做多情绪", "做多仓位", "做多力量", "做多动能", "做多盘",
)
_PREDICTION_WORDS: tuple[str, ...] = (
    "暴涨", "暴跌", "大涨", "大跌", "将涨", "将跌", "会涨", "会跌", "要涨", "要跌",
    "看涨", "看跌", "续涨", "续跌", "补涨", "涨到", "跌到", "上看", "下看",
    "拉升", "冲高", "冲顶", "探底", "启动", "翻倍", "新高", "新低",
    "即将", "将要", "将会", "有望", "料将", "预计", "后市", "下一步", "未来", "接下来",
)
_PRICE_REACHED_ALLOW: tuple[str, ...] = (
    "已跌至", "已涨至", "回落至", "回升至", "运行至",
    "现跌至", "现涨至", "下探至", "上探至", "回踩至",
)
# 突破/破位 只拦【预测性】语境(陈述「无突破/未突破/突破信号」放行)· = compliance._PREDICTION_RES
_PREDICTION_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(即将|将要|将会|将|有望|预计|料将|快要|很快|马上|或将|势必|会)(突破|破位)"),
    re.compile(r"(突破|破位)(在即|可期)"),
)
_PROFIT_WORDS: tuple[str, ...] = (
    "翻倍", "稳赚", "保本", "收益率", "回报率", "躺赚", "财富自由", "一夜暴富", "百倍", "十倍",
)
_DISCLAIMERS: tuple[str, ...] = (
    "仅供参考", "不构成投资建议", "非投资建议", "风险自担", "自行决策",
)
_MAX_LEN = 700


def _hits(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if w in text]


def validate_tweet(text: str) -> tuple[bool, list[str]]:
    """= compliance.validate_tweet · 返回 (passed, reasons)。营销/声明查原文,其余查剥声明 body。"""
    raw = (text or "").strip()
    reasons: list[str] = []
    if not raw:
        return False, ["空文本"]
    if has_marketing_violation(raw):
        reasons.append("营销违规话术(稳赚/保证收益/无风险等)")
    if not any(d in raw for d in _DISCLAIMERS):
        reasons.append("缺免责声明(需含 仅供参考 / 不构成投资建议)")
    body = raw
    for disc in _DISCLAIMERS:
        body = body.replace(disc, "")
    if hits := _hits(body, _ACTION_WORDS):
        reasons.append(f"买卖引导词:{'/'.join(hits)}")
    pred = _hits(body, _PREDICTION_WORDS)
    pred += [m.group(0) for rgx in _PREDICTION_RES if (m := rgx.search(body))]
    if pred:
        reasons.append(f"预测未来走势词:{'/'.join(pred)}")
    hedge_body = body
    for ph in _HEDGE_STATE_ALLOW:
        hedge_body = hedge_body.replace(ph, "")
    if hits := _hits(hedge_body, ("做空", "做多")):
        reasons.append(f"买卖引导词(做空/做多·非陈述):{'/'.join(hits)}")
    price_body = body
    for ph in _PRICE_REACHED_ALLOW:
        price_body = price_body.replace(ph, "")
    if hits := _hits(price_body, ("涨至", "跌至")):
        reasons.append(f"预测未来走势词(涨至/跌至·非陈述):{'/'.join(hits)}")
    if hits := _hits(body, _PROFIT_WORDS):
        reasons.append(f"收益承诺词:{'/'.join(hits)}")
    if len(raw) > _MAX_LEN:
        reasons.append(f"过长({len(raw)} 字 · 超 {_MAX_LEN})")
    return not reasons, reasons


# ════════ prompt + 形态数据(内联 · = x_marketing/tweet_gen.py)════════
_SYSTEM = (
    "你是加密永续技术分析编辑,为点金 Midas 写中文 X(推特)帖。"
    "你【只】客观描述给定的【当前】技术结构事实,绝不预测未来、不给操作建议。\n"
    "结构(★自然成文 · 不要写『【大白话结论】』『【专业技术分析】』之类标签字样):\n"
    "  ① 开头直接一句大白话结论:普通人秒懂的当前状态(如『STG 短期偏弱、运行于下轨』;"
    "偏强/偏弱/震荡 = 偏多/偏空/中性 的通俗说法);\n"
    "  ② 自然过渡到专业技术细节:★只用【给定数据】(布林结构 / 通道位置 %B / 24h 涨跌 / 资金费率);"
    "★给定哪些就说哪些,没给的指标(如未提供 MACD / 缠论 具体数值)直接略过不提,"
    "绝不写『未提供具体数值』『暂无数据』之类露怯的话;\n"
    "  ③ 结尾免责:『仅供参考,不构成投资建议』。\n"
    "硬性规则(违者作废 · ★大白话开头和专业部分【一样严】):\n"
    "1. 倾向只能用『偏多/偏空/中性』及通俗版『偏强/偏弱/震荡』,禁『看涨/将涨/突破在即』等预测词;\n"
    "2. 禁止任何买卖引导(买入/卖出/建议/抄底/止损/加仓/布局/上车…)、目标价、收益承诺;\n"
    "3. 禁止未来时态(即将/将会/有望/预计/后市…),只陈述此刻;可如实报 24h 涨跌幅(事实)但不据此预测;\n"
    "4. ★用词偏好:用『空头/多头动能强』『处于低位/运行于下轨』等中性说法,少碰边界词;\n"
    "5. 不要自己加话题标签 #(由系统统一拼接);整体通俗易懂,中文,300–480 字,结尾必须带免责。"
)


@dataclass(frozen=True)
class Ctx:
    symbol: str
    price: float
    change_pct_24h: float
    bias: str
    state_label: str
    zone_label: str
    pct_b: float
    funding_rate: float


def build_user_prompt(c: Ctx) -> str:
    return (
        f"币种:{c.symbol}(加密永续)\n"
        f"结构倾向(布林):{c.bias}\n"
        f"当前结构:{c.state_label}\n"
        f"通道位置:{c.zone_label}(%B={c.pct_b:.2f})\n"
        f"最新价:{c.price:g}\n"
        f"24h 涨跌幅:{c.change_pct_24h:+.2f}%\n"
        f"资金费率:{c.funding_rate * 100:+.4f}%\n"
        "\n据以上【当前事实】写一条合规技术分析推文(遵守 system 全部规则)。"
    )


_BRAND_TAG = "#点金Midas"


def append_tags(text: str, symbol: str) -> str:
    """末尾拼接 #币种 + #点金Midas(代码侧 · 不依赖 AI · 标签纯标识不触发门禁)。"""
    base = symbol.upper().removesuffix("USDT").removesuffix("USD") or symbol.upper()
    return f"{text.rstrip()}\n#{base} {_BRAND_TAG}"


# 回退 mock(★只在读不到 boll 快照时用 · 覆盖三倾向 · 保证脚本任何环境能跑出批量逻辑)
_FALLBACK: list[Ctx] = [
    Ctx("BTCUSDT", 61744.1, 3.2, "偏多", "三线齐上·上升结构", "近上轨", 0.92, 0.0001),
    Ctx("SOLUSDT", 142.5, 5.1, "偏多", "带宽开口·向上", "破上轨", 1.04, 0.0002),
    Ctx("ETHUSDT", 2980.5, -2.1, "中性", "三线走平·震荡结构", "近中轨", 0.48, -0.00005),
    Ctx("SIRENUSDT", 0.0362, -8.4, "偏空", "带宽开口·向下", "破下轨", -0.05, 0.0003),
    Ctx("XYZUSDT", 1.23, -6.7, "偏空", "三线齐跌·下降结构", "近下轨", 0.06, 0.0004),
]
_SNAPSHOT_KEY = "boll:snapshot:latest"  # 做T A-1 快照(worker 落 · 本脚本只读挑币)


def _to_ctx(row: dict[str, Any]) -> Ctx:
    """boll 快照行 → Ctx(price=close · None 容错为 0.0 · 只作生成素材)。"""
    return Ctx(
        symbol=str(row["symbol"]),
        price=float(row.get("close") or 0.0),
        change_pct_24h=float(row.get("change_pct_24h") or 0.0),
        bias=str(row.get("bias") or "中性"),
        state_label=str(row.get("state_label") or "—"),
        zone_label=str(row.get("zone_label") or "—"),
        pct_b=float(row.get("pct_b") or 0.5),
        funding_rate=float(row.get("funding_rate") or 0.0),
    )


async def _pick_coins() -> list[Ctx]:
    """从 boll 快照按 bias 挑代表性币:★强偏空 5(最该压测)+ 强偏多 5 + 中性 4 = 最多 14。

    读不到快照(本地无 Redis / worker 没落)→ 回退 _FALLBACK(批量逻辑照样验)。
    """
    try:
        redis = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
        )
        raw = await redis.get(_SNAPSHOT_KEY)
        await redis.aclose()
    except Exception as exc:  # noqa: BLE001 · 读不到就回退,不让脚本崩
        print(f"(读 boll 快照失败 · 回退内置 mock:{exc})")
        return _FALLBACK
    items: list[dict[str, Any]] = json.loads(raw).get("items", []) if raw else []
    if not items:
        print("(boll 快照为空 · 回退内置 mock)")
        return _FALLBACK

    def _of(bias: str) -> list[dict[str, Any]]:
        return [x for x in items if x.get("bias") == bias]

    shorts = sorted(_of("偏空"), key=lambda x: x.get("pct_b", 0.5))[:5]          # %B 低在前 = 最空
    longs = sorted(_of("偏多"), key=lambda x: -x.get("pct_b", 0.5))[:5]          # %B 高在前 = 最多
    neutral = sorted(_of("中性"), key=lambda x: abs(x.get("pct_b", 0.5) - 0.5))[:4]
    return [_to_ctx(x) for x in (*shorts, *longs, *neutral)]  # ★偏空在前(最该看)


async def main() -> None:
    mode = "MOCK(★容器没读到 DEEPSEEK_API_KEY!)" if is_mock_mode() else "真 DeepSeek"
    coins = await _pick_coins()
    print(f"LLM 模式:{mode} · 批量 {len(coins)} 条(偏空优先)\n" + "=" * 70)
    passed_n = 0
    rejects: list[str] = []
    for c in coins:
        resp = await ainvoke(build_user_prompt(c), system=_SYSTEM)
        tweet = append_tags(resp.content, c.symbol)  # ★拼标签后再过门禁(印的=将发的)
        passed, reasons = validate_tweet(tweet)
        src = "mock" if resp.is_mock else "DeepSeek"
        print(f"\n── {c.symbol}({c.bias} · {c.state_label})  [{src}]")
        print(f"  推文:{tweet}")
        if passed:
            passed_n += 1
            print("  门禁:✅ 通过")
        else:
            rejects.append(f"{c.symbol}({c.bias}):{' | '.join(reasons)}")
            print(f"  门禁:❌ 否决 · {' | '.join(reasons)}")
    print("\n" + "=" * 70)
    print(f"汇总:共 {len(coins)} 条 · 通过 {passed_n} · 否决 {len(coins) - passed_n}")
    for r in rejects:
        print(f"  ❌ {r}")


if __name__ == "__main__":
    asyncio.run(main())
