"""X 营销自动托管 · 自动起草编排(PR-2)单测:守卫 skip 全分支 + happy + 6h 去重。

DB(midas_test · CI)+ FakeRedis(开关/熔断/配额/去重 + 快照)+ mock LLM(不打 DeepSeek)。
★门禁硬拦:happy 用例验只有 compliance_passed 的进 passed。
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.visit_stats import CN_TZ
from app.services.x_marketing import auto_draft
from app.services.x_marketing import generate as gen
from app.services.x_marketing.publish import auto_guard
from app.services.x_marketing.store import list_recent
from app.services.x_marketing.tweet_gen import TweetContext

_SNAP = "boll:snapshot:latest"


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)

    async def set(self, k: str, v: Any, ex: int | None = None) -> None:  # noqa: ARG002
        self.kv[k] = v

    async def delete(self, k: str) -> None:
        self.kv.pop(k, None)

    async def incr(self, k: str) -> int:
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    async def expire(self, k: str, ttl: int) -> None:
        pass


def _snap_item(symbol: str, change: float, *, transition: bool) -> dict[str, Any]:
    return {
        "symbol": symbol, "bias": "偏空", "pct_b": 0.05, "close": 1.5,
        "state_label": "带宽开口·向下", "zone_label": "破下轨",
        "change_pct_24h": change, "funding_rate": 0.0001, "transition": transition,
    }


def _seed_snapshot(r: _FakeRedis, items: list[dict[str, Any]]) -> None:
    r.kv[_SNAP] = json.dumps({"items": items})


def _in_window() -> datetime:
    return datetime(2026, 6, 27, 13, 0, tzinfo=CN_TZ)  # 13:00 CST · 窗内


def _mock_compliant_llm(monkeypatch) -> None:  # noqa: ANN001
    async def fake_gen(ctx: TweetContext, *_: object) -> object:  # *_ 吃 style 参数
        return SimpleNamespace(
            content=f"${ctx.symbol} 偏空,运行于下轨下方。以上为当前结构。仅供参考,不构成投资建议。",
            is_mock=True,
        )
    monkeypatch.setattr(gen, "generate_tweet_text", fake_gen)


# ── 守卫 skip 全分支 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skip_when_disabled(db_session) -> None:  # noqa: ANN001
    r = _FakeRedis()  # 开关默认 OFF
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())
    assert out == {"status": "skip", "reason": "disabled"}


@pytest.mark.asyncio
async def test_skip_when_circuit_open(db_session) -> None:  # noqa: ANN001
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    await auto_guard.open_circuit(r)
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())
    assert out["reason"] == "circuit_open"


@pytest.mark.asyncio
async def test_skip_out_of_window(db_session) -> None:  # noqa: ANN001
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    out = await auto_draft.run_auto_draft(
        db_session, r, now=datetime(2026, 6, 27, 3, 0, tzinfo=CN_TZ),  # 03:00 窗外
    )
    assert out["reason"] == "out_of_window"


@pytest.mark.asyncio
async def test_skip_daily_cap(db_session) -> None:  # noqa: ANN001
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    now = _in_window()
    r.kv[auto_guard._daily_key(now)] = auto_guard.AUTO_DAILY_MAX  # 顶到 30
    out = await auto_draft.run_auto_draft(db_session, r, now=now)
    assert out["reason"] == "daily_cap"


@pytest.mark.asyncio
async def test_skip_no_candidates_empty_snapshot(db_session) -> None:  # noqa: ANN001
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())  # 无快照
    assert out["reason"] == "no_candidates"


# ── happy:每轮 2 条都起草,★只 rows[0] 进自动发(频率调整 · 调整A)──────────


@pytest.mark.asyncio
async def test_drafts_two_but_publishes_only_first(db_session, monkeypatch) -> None:  # noqa: ANN001
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    _seed_snapshot(r, [
        _snap_item("AAAUSDT", -2.0, transition=False),  # 非转换 → 不选
        _snap_item("BBBUSDT", -9.0, transition=True),   # |9| 最大 → rows[0] → 自动发
        _snap_item("CCCUSDT", 4.0, transition=True),    # |4| → rows[1] → 留后台补发
        _snap_item("DDDUSDT", 1.0, transition=True),    # 超 limit 不选
    ])
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())
    assert out["status"] == "ok"
    # ★两条都起草存后台
    assert {s for _, s in out["drafted"]} == {"BBBUSDT", "CCCUSDT"}
    # ★只自动发 rows[0](|change| 最大 = BBB)· 第 2 条 CCC 不进自动发队列
    assert out["auto_publish"] is not None
    assert out["auto_publish"][1] == "BBBUSDT"
    # ★auto_drafted=True 标记(待补发素材识别 + 计入日配额)
    rows = await list_recent(db_session)
    drafted = [row for row in rows if row.symbol in {"BBBUSDT", "CCCUSDT"}]
    assert len(drafted) == 2
    assert all(row.auto_drafted for row in drafted)


@pytest.mark.asyncio
async def test_understanding_b_first_dedup_promotes_second(
    db_session, monkeypatch,  # noqa: ANN001
) -> None:
    # ★理解B 核心:rows[0] 6h 去重命中 → ★顺延发 rows[1](不是整轮跳过)
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    await auto_guard.mark_published(r, "BBBUSDT")  # rows[0] 近 6h 发过
    _seed_snapshot(r, [
        _snap_item("BBBUSDT", -9.0, transition=True),  # rows[0] · 被去重挡
        _snap_item("CCCUSDT", 4.0, transition=True),   # rows[1] · 可发
    ])
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())
    assert out["status"] == "ok"
    assert {s for _, s in out["drafted"]} == {"BBBUSDT", "CCCUSDT"}  # 两条都起草
    # ★理解B:rows[0] 重复 → 顺延发 rows[1]=CCC(★仍只发 1 条 · 单 target)
    assert out["auto_publish"] is not None
    assert out["auto_publish"][1] == "CCCUSDT"


@pytest.mark.asyncio
async def test_understanding_b_first_gate_fail_promotes_second(
    db_session, monkeypatch,  # noqa: ANN001
) -> None:
    # ★理解B:rows[0] 门禁未过 → 顺延发 rows[1](合规那条)
    async def fake_gen(ctx: TweetContext, *_: object) -> object:  # *_ 吃 style 参数
        bad = "建议逢低买入"  # 买卖祈使 → 门禁拦
        body = bad if ctx.symbol == "BBBUSDT" else "偏空,运行于下轨下方"
        return SimpleNamespace(
            content=f"${ctx.symbol} {body}。仅供参考,不构成投资建议。", is_mock=True,
        )

    monkeypatch.setattr(gen, "generate_tweet_text", fake_gen)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    _seed_snapshot(r, [
        _snap_item("BBBUSDT", -9.0, transition=True),  # rows[0] · 门禁未过
        _snap_item("CCCUSDT", 4.0, transition=True),   # rows[1] · 合规
    ])
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())
    assert out["status"] == "ok"
    assert {s for _, s in out["drafted"]} == {"BBBUSDT", "CCCUSDT"}
    # ★rows[0] 门禁未过 → 顺延发 rows[1]=CCC
    assert out["auto_publish"] is not None
    assert out["auto_publish"][1] == "CCCUSDT"


@pytest.mark.asyncio
async def test_understanding_b_both_blocked_no_publish(
    db_session, monkeypatch,  # noqa: ANN001
) -> None:
    # ★理解B:两条都被挡(6h 去重)→ 不发(target=None)· 这轮空档
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    await auto_guard.mark_published(r, "BBBUSDT")  # 两条都近 6h 发过
    await auto_guard.mark_published(r, "CCCUSDT")
    _seed_snapshot(r, [
        _snap_item("BBBUSDT", -9.0, transition=True),
        _snap_item("CCCUSDT", 4.0, transition=True),
    ])
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())
    assert out["status"] == "ok"
    assert {s for _, s in out["drafted"]} == {"BBBUSDT", "CCCUSDT"}  # 仍都起草
    assert out["auto_publish"] is None  # ★两条都被挡 → 不发
