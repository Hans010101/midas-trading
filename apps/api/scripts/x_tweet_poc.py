"""X 营销阶段2 POC 跑测(影子 · 不发 X)。

两段:
  ① 门禁有效性证明:对【违禁推文】+【合规范例】跑 validate_tweet 打印判决(纯代码 · 任何环境可跑)。
  ② 生成管线:对几个 mock 形态调 generate_tweet_text(无 key 自动 mock · 服务器配 key 则真 DeepSeek)
     → 过门禁 → 打印【币种 / 推文 / 是否 mock / 门禁结果】。★只打印,绝不发 X。

跑:cd apps/api && .venv/bin/python scripts/x_tweet_poc.py
"""

from __future__ import annotations

import asyncio

from app.services.x_marketing.compliance import validate_tweet
from app.services.x_marketing.tweet_gen import TweetContext, generate_tweet_text

_VIOLATING = [
    ("买卖引导", "$BTC 偏多,建议逢低买入,止损放下轨。仅供参考,不构成投资建议。"),
    ("预测未来", "$ETH 即将突破前高,看涨,上看 4000。仅供参考,不构成投资建议。"),
    ("收益承诺", "$SOL 偏多,持有有望翻倍,躺赚。仅供参考,不构成投资建议。"),
    ("营销违规", "$BTC 偏多,稳赚不赔,放心拿。仅供参考,不构成投资建议。"),
    ("缺免责", "$BTC 当前结构偏多,三线齐上,价格近上轨。"),
]
_COMPLIANT = [
    "$BTC 当前布林结构偏多,三线齐上呈上升结构,价格运行于上轨附近(%B=0.92)。"
    "MACD 红柱温和、DIF 在零轴上方;缠论笔向上、中枢上沿。24h 涨跌幅 +3.20%。"
    "以上为当前结构描述。仅供参考,不构成投资建议。",
    "$ETH 当前结构中性,三线走平呈震荡结构,价格近中轨(%B=0.48)。"
    "24h 涨跌幅 -2.10%,资金费率 +0.0100%。以上为当前结构。仅供参考,不构成投资建议。",
]

_CTX = [
    TweetContext("BTCUSDT", 61744.1, 3.2, "偏多", "三线齐上·上升结构", "近上轨", 0.92, 0.0001),
    TweetContext("ETHUSDT", 2980.5, -2.1, "中性", "三线走平·震荡结构", "近中轨", 0.48, -0.00005),
    TweetContext("SIRENUSDT", 0.0362, -8.4, "偏空", "带宽开口·向下", "破下轨", 0.0, 0.0003),
]


def _verdict(text: str) -> str:
    r = validate_tweet(text)
    return "✅ 通过" if r.passed else f"❌ 否决 · {' | '.join(r.reasons)}"


async def main() -> None:
    print("=" * 70)
    print("① 门禁有效性证明 —— 违禁必拦")
    for tag, t in _VIOLATING:
        r = validate_tweet(t)
        flag = "拦住✓" if not r.passed else "★漏了✗"
        print(f"  [{tag}] {flag}  {' | '.join(r.reasons)}")
    print("\n① 门禁有效性证明 —— 合规必过")
    for t in _COMPLIANT:
        r = validate_tweet(t)
        print(f"  {'通过✓' if r.passed else '★误杀✗ ' + str(r.reasons)}")

    print("\n" + "=" * 70)
    print("② 生成管线(影子 · 不发 X)")
    for ctx in _CTX:
        resp = await generate_tweet_text(ctx)
        tag = "MOCK" if resp.is_mock else "DeepSeek真实"
        print(f"\n── {ctx.symbol}({ctx.bias} · {ctx.state_label})  [{tag}]")
        print(f"  推文:{resp.content}")
        print(f"  门禁:{_verdict(resp.content)}")


if __name__ == "__main__":
    asyncio.run(main())
