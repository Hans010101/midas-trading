"""做T 定时全景(体系1 · M2-3a)纯逻辑单测:分组 / %B 排序 / 前5 / 空组 / 图1样式 / 超链接 / 安静时段。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.ai.boll_digest import (
    DETAIL_URL,
    build_hourly_digest,
    is_global_quiet_hour,
)
from app.services.ai.boll_state import _FORBIDDEN_PUSH_WORDS


def _item(sym: str, bias: str, pct_b: float, *, change: float | None = 1.0) -> dict:
    return {
        "symbol": sym,
        "bias": bias,
        "pct_b": pct_b,
        "state_label": "带宽开口·向上",
        "zone_label": "近上轨",
        "change_pct_24h": change,
    }


def test_groups_and_top5_by_pctb() -> None:
    # 偏多 7 个(按 %B 高→低取前5)· 偏空 2 个(按 %B 低→高)· 中性 1 个
    items = [_item(f"L{i}USDT", "偏多", 0.5 + i * 0.1) for i in range(7)]  # %B 0.5..1.1
    items += [_item("S1USDT", "偏空", 0.05), _item("S2USDT", "偏空", -0.1)]
    items += [_item("N1USDT", "中性", 0.5, change=3.0)]
    msg = build_hourly_digest(items, as_of_label="14:00")
    assert msg is not None
    assert msg.startswith("📊 做T扫描 · 14:00")
    # 三组标题(方向 emoji · 非红绿)+ 全量计数
    assert "📈 偏多(7)" in msg
    assert "📉 偏空(2)" in msg
    assert "➖ 中性(1)" in msg
    # ★偏多取前5 = %B 最高的 L6..L2(L0/L1 被截);偏多组只 5 行
    assert "L6USDT" in msg
    assert "L5USDT" in msg
    assert "L0USDT" not in msg
    assert "L1USDT" not in msg
    # ★偏空按 %B 低→高:S2(-0.1)在 S1(0.05)之前
    assert msg.index("S2USDT") < msg.index("S1USDT")


def test_hyperlink_format() -> None:
    msg = build_hourly_digest([_item("BTCUSDT", "偏多", 0.9, change=5.2)], as_of_label="09:00")
    assert msg is not None
    # ★Markdown 超链接指向详情页(parse_mode=Markdown)
    assert f"[BTCUSDT]({DETAIL_URL}?symbol=BTCUSDT)" in msg
    # 单币行:状态 · 通道位置(%B) · 24h涨跌
    assert "带宽开口·向上" in msg
    assert "近上轨(%B=0.90)" in msg
    assert "+5.2%" in msg


def test_empty_group_omitted_and_change_none() -> None:
    # 只有偏多 → 中性/偏空组省略;change=None → 显示「—」
    msg = build_hourly_digest([_item("AUSDT", "偏多", 0.8, change=None)], as_of_label="10:00")
    assert msg is not None
    assert "📈 偏多(1)" in msg
    assert "➖ 中性" not in msg
    assert "📉 偏空" not in msg
    assert "· —" in msg  # change None 兜底


def test_all_empty_returns_none() -> None:
    # 无快照 / 无有效结构 → None(不推)
    assert build_hourly_digest([], as_of_label="11:00") is None


def test_disclaimer_and_no_trade_words() -> None:
    # ★末尾「· 仅供参考」(过门禁)· 全文无买卖/预测词
    items = [_item("BTCUSDT", "偏多", 0.9), _item("ETHUSDT", "偏空", 0.1)]
    msg = build_hourly_digest(items, as_of_label="12:00")
    assert msg is not None
    assert msg.rstrip().endswith("· 仅供参考")
    body = msg.replace("仅供参考", "")
    for word in _FORBIDDEN_PUSH_WORDS:
        assert word not in body


def test_global_quiet_hour() -> None:
    # 夜间(CST 02:00 = UTC 18:00 前一日)→ 安静跳过;白天(CST 14:00 = UTC 06:00)→ 推
    night = datetime(2026, 6, 24, 18, 0, tzinfo=UTC)  # CST 次日 02:00
    day = datetime(2026, 6, 24, 6, 0, tzinfo=UTC)      # CST 14:00
    assert is_global_quiet_hour(night) is True
    assert is_global_quiet_hour(day) is False
