"""共享数值格式化 · 价格动态精度规则(单一事实源)。

价格按数量级动态小数位(产品规格 · 边界归属写死在下面):
- |v| ≥ 1000        → 0 位(整数,如 BTC 95234)
- 100 ≤ |v| < 1000  → 1 位
- 1   ≤ |v| < 100   → 2 位
- |v| < 1           → 最多 8 位、去尾零(0.5→0.5;0.00012345→0.00012345)

★ 只作用于「价格」类显示(行情价 / 预估价 / 成交价 / 强平价 / 名义 等)。
盈亏(pnl)/ 手续费(fee)/ 账户余额是「金额类」,固定精度、不走本规则。
bot(replies.py · TG+飞书共享)与通知(templates.py · 含 bot 成交回执 body)各自的价格
格式化都引用本函数 —— 改这一处,两层(进而 TG+飞书+推送)价格精度一起生效。

红线:这里只决定「显示几位小数」,不碰任何金额【计算】(撮合 / 盈亏 / 手续费一行不动)。
"""

from __future__ import annotations

_PRICE_INT_FROM = 1000.0  # ≥ 此值 → 0 位
_PRICE_1DP_FROM = 100.0  # ≥ 此值(< 1000)→ 1 位
_PRICE_2DP_FROM = 1.0  # ≥ 此值(< 100)→ 2 位;< 1 → 8 位

_DECIMALS_INT = 0
_DECIMALS_1DP = 1
_DECIMALS_2DP = 2
_DECIMALS_SUB1 = 8


def price_decimals(value: float) -> int:
    """价格显示小数位 · 按 |value| 数量级区间。

    边界归属:≥1000→0 位 · ≥100<1000→1 位 · ≥1<100→2 位 · <1→8 位。
    用 abs() 决定数量级(价格恒为正,防御性处理负值/0:0 归入 <1 → 8 位)。
    """
    magnitude = abs(value)
    if magnitude >= _PRICE_INT_FROM:
        return _DECIMALS_INT
    if magnitude >= _PRICE_1DP_FROM:
        return _DECIMALS_1DP
    if magnitude >= _PRICE_2DP_FROM:
        return _DECIMALS_2DP
    return _DECIMALS_SUB1


def format_price_number(value: float) -> str:
    """价格数字串(千分位 + 动态小数位)· 单一事实源 · 不含币种符号。

    两个通道的价格格式化(replies._fmt_price / templates._fmt_price)都套这一函数,
    只在外层补各自的币种符号 / 后缀 —— 改这里,TG + 飞书 + 推送同步生效。

    <1 档(8 位)去掉末尾多余的 0(0.50000000 → 0.5;0.00012345 完整保留);
    ≥1 各档(0 / 1 / 2 位)按位数原样保留、不去零(95234 / 523.4 / 12.35)。
    """
    decimals = price_decimals(value)
    text = f"{value:,.{decimals}f}"
    if decimals == _DECIMALS_SUB1:  # 仅 <1 档去尾零;其余档整数 / 定位小数不动
        text = text.rstrip("0").rstrip(".")
    return text
