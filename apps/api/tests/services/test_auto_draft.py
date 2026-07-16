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
    r.kv[auto_guard._daily_key(now)] = auto_guard.AUTO_DAILY_MAX  # 顶到日上限
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


# ── ★step1:X 短推独立自动起草(run_auto_draft_xshort · 手动发 · 永不自动发)────


@pytest.mark.asyncio
async def test_xshort_drafts_when_enabled(db_session, monkeypatch) -> None:  # noqa: ANN001
    """happy:开关开 + 窗内 + 有配额 + 有候选 → 生成 x_short draft(gen_style=x_short · auto_drafted)。

    ★返回 list(不是 dict · 结构上永不含 auto_publish target)· x_short 只能人工发。
    """
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    _seed_snapshot(r, [
        _snap_item("BBBUSDT", -9.0, transition=True),
        _snap_item("CCCUSDT", 4.0, transition=True),
    ])
    out = await auto_draft.run_auto_draft_xshort(db_session, r, now=_in_window())
    assert isinstance(out, list)                       # ★永不返回 target,只 (id,sym) 列表
    assert {s for _, s in out} == {"BBBUSDT", "CCCUSDT"}
    rows = await list_recent(db_session)
    xs = [row for row in rows if row.symbol in {"BBBUSDT", "CCCUSDT"}]
    assert len(xs) == 2
    assert all(row.gen_style == "x_short" for row in xs)   # ★gen_style=x_short
    assert all(row.auto_drafted for row in xs)             # ★auto_drafted(🤖自动)
    assert int(r.kv[auto_guard._xshort_draft_key(_in_window())]) == 2  # ★独立配额键 +2


@pytest.mark.asyncio
async def test_xshort_skip_when_disabled(db_session) -> None:  # noqa: ANN001
    r = _FakeRedis()  # 总开关 OFF → x_short 也不起草
    out = await auto_draft.run_auto_draft_xshort(db_session, r, now=_in_window())
    assert out == []


@pytest.mark.asyncio
async def test_xshort_skip_out_of_window(db_session, monkeypatch) -> None:  # noqa: ANN001
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    _seed_snapshot(r, [_snap_item("BBBUSDT", -9.0, transition=True)])
    out = await auto_draft.run_auto_draft_xshort(
        db_session, r, now=datetime(2026, 6, 27, 3, 0, tzinfo=CN_TZ),  # 03:00 窗外
    )
    assert out == []


@pytest.mark.asyncio
async def test_xshort_skip_when_quota_exhausted(db_session, monkeypatch) -> None:  # noqa: ANN001
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    now = _in_window()
    r.kv[auto_guard._xshort_draft_key(now)] = auto_guard.XSHORT_DRAFT_DAILY_MAX  # 顶格
    _seed_snapshot(r, [_snap_item("BBBUSDT", -9.0, transition=True)])
    out = await auto_draft.run_auto_draft_xshort(db_session, r, now=now)
    assert out == []


@pytest.mark.asyncio
async def test_xshort_quota_independent_of_binance_cap(db_session, monkeypatch) -> None:  # noqa: ANN001
    """★核心独立性:币安发布配额顶格(daily_cap)→ 币安 skip,但 x_short 仍照常起草(不被挤占)。"""
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    now = _in_window()
    r.kv[auto_guard._daily_key(now)] = auto_guard.AUTO_DAILY_MAX  # 币安顶到日上限
    _seed_snapshot(r, [
        _snap_item("BBBUSDT", -9.0, transition=True),
        _snap_item("CCCUSDT", 4.0, transition=True),
    ])
    binance = await auto_draft.run_auto_draft(db_session, r, now=now)
    assert binance["reason"] == "daily_cap"                # 币安被日配额挡
    xs = await auto_draft.run_auto_draft_xshort(db_session, r, now=now)
    assert {s for _, s in xs} == {"BBBUSDT", "CCCUSDT"}    # ★x_short 不受影响,照常起草
    # ★x_short 没动币安配额键(仍 = MAX,没多加)
    assert int(r.kv[auto_guard._daily_key(now)]) == auto_guard.AUTO_DAILY_MAX


# ── ★step1:merge_xshort_drafted 纯函数(红线边界 · x_short 绝不进 auto_publish)──────
#   纯函数不需 PG,本地即跑,直接钉死 manual-first 的合并边界(自审 nit1)。


def test_merge_xshort_into_drafted_not_autopublish() -> None:
    """★核心红线:x_short 只并入 drafted、绝不进 auto_publish;币安 target 原样保留。"""
    binance = {"status": "ok", "drafted": [(1, "BTCUSDT")], "auto_publish": (1, "BTCUSDT")}
    out = auto_draft.merge_xshort_drafted(binance, [(2, "ETHUSDT"), (3, "SOLUSDT")])
    assert set(out["drafted"]) == {(1, "BTCUSDT"), (2, "ETHUSDT"), (3, "SOLUSDT")}  # 都进截图
    assert out["auto_publish"] == (1, "BTCUSDT")  # ★仍是币安 target · x_short 没混进自动发
    xshort_ids = {2, 3}
    assert out["auto_publish"][0] not in xshort_ids  # ★双证:auto_publish 的 id 绝非 x_short


def test_merge_xshort_when_binance_skipped_no_autopublish() -> None:
    """币安 skip(无 auto_publish 键)+ x_short 有货 → status 提 ok、drafted=xs、★auto_publish 仍 None。"""
    binance = {"status": "skip", "reason": "daily_cap"}   # 币安被日配额挡 · 无 auto_publish 键
    out = auto_draft.merge_xshort_drafted(binance, [(2, "ETHUSDT")])
    assert out["status"] == "ok"                  # 提为 ok 触发截图分支
    assert out["drafted"] == [(2, "ETHUSDT")]
    assert out.get("auto_publish") is None        # ★x_short 永不自动发(排发拿到 None)


def test_merge_xshort_empty_unchanged() -> None:
    """x_short 空 → result 原样(不加 drafted、不改 status)。"""
    binance = {"status": "skip", "reason": "disabled"}
    out = auto_draft.merge_xshort_drafted(binance, [])
    assert out == {"status": "skip", "reason": "disabled"}


# ── ★生成侧 6h 去重(两平台统一规则:每轮最强 N + 6h 不重复)──────────────


@pytest.mark.asyncio
async def test_gen_dedup_skips_recently_generated(db_session, monkeypatch) -> None:  # noqa: ANN001
    """★6h 内已起草的币被剔除,顺延到次强 fresh 币(每轮仍取最强 N·防同币 15min 刷屏)。"""
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    await auto_guard.mark_generated(r, "default", "BBBUSDT")  # BBB(|9|最强)6h 内已起草 → 剔除
    _seed_snapshot(r, [
        _snap_item("BBBUSDT", -9.0, transition=True),  # 最强但已起草 → 跳过
        _snap_item("CCCUSDT", 4.0, transition=True),   # 次强 fresh → 起草
        _snap_item("DDDUSDT", 1.0, transition=True),   # 再次 fresh → 起草(补满 2)
    ])
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())
    assert out["status"] == "ok"
    # ★BBB 被 6h 去重剔除 → 起草次强两个 fresh(CCC+DDD)· 不含 BBB
    assert {s for _, s in out["drafted"]} == {"CCCUSDT", "DDDUSDT"}
    # ★新起草的被标记 6h(下轮不再重复)
    assert await auto_guard.is_recently_generated(r, "default", "CCCUSDT") is True
    assert await auto_guard.is_recently_generated(r, "default", "DDDUSDT") is True


@pytest.mark.asyncio
async def test_gen_dedup_all_recent_skips_round(db_session, monkeypatch) -> None:  # noqa: ANN001
    """★候选全在 6h 内已起草 → 本轮无 fresh → skip no_candidates(不重复刷屏)。"""
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    await auto_guard.mark_generated(r, "default", "BBBUSDT")
    await auto_guard.mark_generated(r, "default", "CCCUSDT")
    _seed_snapshot(r, [
        _snap_item("BBBUSDT", -9.0, transition=True),
        _snap_item("CCCUSDT", 4.0, transition=True),
    ])
    out = await auto_draft.run_auto_draft(db_session, r, now=_in_window())
    assert out == {"status": "skip", "reason": "no_candidates"}


@pytest.mark.asyncio
async def test_gen_dedup_xshort_independent_from_binance(db_session, monkeypatch) -> None:  # noqa: ANN001
    """★x_short 生成去重与币安独立:币安起草过 BBB 不挡 x_short 起草 BBB(各自 gen_style 键)。"""
    _mock_compliant_llm(monkeypatch)
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    await auto_guard.mark_generated(r, "default", "BBBUSDT")  # 只币安线标了 BBB
    _seed_snapshot(r, [_snap_item("BBBUSDT", -9.0, transition=True)])
    xs = await auto_draft.run_auto_draft_xshort(db_session, r, now=_in_window())
    assert {s for _, s in xs} == {"BBBUSDT"}  # ★x_short 线不受币安标记影响,照常起草 BBB
    assert await auto_guard.is_recently_generated(r, "x_short", "BBBUSDT") is True  # x_short 线标了
