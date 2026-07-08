"""每日推文生成流程(阶段4a · PR-2)单测:pick_contexts 选币(纯)+ generate_and_store(DB+mock LLM)。

pick_contexts 纯逻辑(任何环境)· generate_and_store DB 测(midas_test · CI 跑)+ mock DeepSeek。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.x_marketing import generate as gen
from app.services.x_marketing.generate import pick_contexts
from app.services.x_marketing.store import list_recent
from app.services.x_marketing.tweet_gen import TweetContext


def _row(symbol: str, bias: str, pct_b: float) -> dict[str, Any]:
    return {
        "symbol": symbol, "bias": bias, "pct_b": pct_b, "close": 1.5,
        "state_label": "三线走平·震荡结构", "zone_label": "近中轨",
        "change_pct_24h": -2.0, "funding_rate": 0.0001,
    }


def test_pick_contexts_short_first_and_maps_fields() -> None:
    # ★偏空优先 + close→price + 各倾向按 %B 极端度排
    items = [
        _row("L1USDT", "偏多", 0.95), _row("L2USDT", "偏多", 0.70),
        _row("S1USDT", "偏空", 0.02), _row("S2USDT", "偏空", 0.20),
        _row("N1USDT", "中性", 0.50),
    ]
    ctxs = pick_contexts(items)
    syms = [c.symbol for c in ctxs]
    # 偏空(%B 低在前)→ 偏多(%B 高在前)→ 中性
    assert syms == ["S1USDT", "S2USDT", "L1USDT", "L2USDT", "N1USDT"]
    assert ctxs[0].bias == "偏空"
    assert ctxs[0].price == 1.5  # close → price
    assert isinstance(ctxs[0], TweetContext)


def test_pick_contexts_respects_caps() -> None:
    items = [_row(f"S{i}USDT", "偏空", i * 0.01) for i in range(10)]
    ctxs = pick_contexts(items, n_short=3, n_long=5, n_neutral=4)
    assert len(ctxs) == 3  # 偏空只取前 3


# ── 自动托管选币(口径 b · transition + |change| 降序)──────────────────────


def _auto_row(symbol: str, change: float, *, transition: bool) -> dict[str, Any]:
    r = _row(symbol, "中性", 0.5)
    r["change_pct_24h"] = change
    r["transition"] = transition
    return r


def test_pick_auto_contexts_transition_and_change_order() -> None:
    from app.services.x_marketing.generate import pick_auto_contexts

    items = [
        _auto_row("A", -3.0, transition=False),  # 非转换 → 排除(即使涨跌大)
        _auto_row("B", -8.0, transition=True),   # 转换 · |8| 最大 → 第一
        _auto_row("C", 5.0, transition=True),    # 转换 · |5| → 第二
        _auto_row("D", 1.0, transition=True),    # 转换 · |1| 最小
    ]
    ctxs = pick_auto_contexts(items, limit=2)
    assert [c.symbol for c in ctxs] == ["B", "C"]  # 仅 transition · |change| 降序 · 取 2


def test_pick_auto_contexts_handles_none_change() -> None:
    from app.services.x_marketing.generate import pick_auto_contexts

    items = [_auto_row("X", 0.0, transition=True)]
    items[0]["change_pct_24h"] = None  # None 当 0 处理,不崩
    ctxs = pick_auto_contexts(items, limit=2)
    assert [c.symbol for c in ctxs] == ["X"]


@pytest.mark.asyncio
async def test_generate_and_store_pass_and_fail(db_session, monkeypatch) -> None:  # noqa: ANN001
    # mock DeepSeek:BTC 合规 / ETH 违规(建议买入)· ★两条都存(不过的记 reason)
    contents = {
        "BTCUSDT": "$BTC 偏多,运行于上轨上方。以上为当前结构。仅供参考,不构成投资建议。",
        "ETHUSDT": "$ETH 偏空,建议逢低买入。仅供参考,不构成投资建议。",
    }

    async def fake_gen(ctx: TweetContext, *_: object) -> object:  # *_ 吃 style 参数
        return SimpleNamespace(content=contents[ctx.symbol], is_mock=True)

    monkeypatch.setattr(gen, "generate_tweet_text", fake_gen)
    ctxs = [
        TweetContext("BTCUSDT", 6.0, 1.0, "偏多", "三线齐上·上升结构", "近上轨", 0.9, 0.0),
        TweetContext("ETHUSDT", 3.0, -1.0, "偏空", "带宽开口·向下", "破下轨", 0.05, 0.0),
    ]
    # ★返回创建的行(id+symbol 供 worker enqueue 截图)· 门禁过/不过都在内
    created = await gen.generate_and_store(db_session, ctxs, generated_by=None)
    assert len(created) == 2
    assert all(r.id is not None for r in created)  # id 已落(供截图 enqueue)
    assert sum(1 for r in created if r.compliance_passed) == 1  # BTC 过 · ETH 不过

    rows = await list_recent(db_session)
    assert len(rows) == 2
    eth = next(r for r in rows if r.symbol == "ETHUSDT")
    assert eth.compliance_passed is False  # ★门禁不过
    assert "买卖引导" in (eth.compliance_reason or "")  # 记了原因
    assert eth.status == "draft"  # 仍止于待发
    assert eth.tweet_text.endswith("#ETH #点金Midas")  # 标签拼了
    assert eth.image_path is None  # ★截图异步回填,此刻仍 null
    btc = next(r for r in rows if r.symbol == "BTCUSDT")
    assert btc.compliance_passed is True
