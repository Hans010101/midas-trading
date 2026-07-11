"""种子枯竭告警(纯监控层)· 覆盖:快枯竭触发/未枯竭不触发/去抖/TG未配置/★仅种子非滚动源。

★验证告警真会响(任务要求):test_maybe_alert_sends 断言 telegram.send 真被调 + 文案含种子;
test_run_check_end_to_end 端到端(DB→筛→告警);阈值 override 覆盖「调大立即触发」验证手段。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services.econ_calendar import seed_alert

_NOW = datetime(2026, 7, 11, tzinfo=UTC)


# ── 纯函数:阈值筛选 ─────────────────────────────────────────────────────


def test_depleting_threshold():
    seeds = [
        ("cn_gdp", datetime(2026, 9, 1, tzinfo=UTC)),   # ~1.7 月 → 告警
        ("boj", datetime(2026, 12, 18, tzinfo=UTC)),    # ~5.2 月 → 不告
        ("ecb", datetime(2027, 12, 16, tzinfo=UTC)),    # ~17 月 → 不告
    ]
    dep = seed_alert.depleting(seeds, _NOW, months=3.0)
    assert [d["event_type"] for d in dep] == ["cn_gdp"]
    assert dep[0]["months_left"] < 3


def test_depleting_naive_datetime_tolerated():
    """DB 可能返 naive datetime → 按 UTC 处理不崩。"""
    dep = seed_alert.depleting([("cn_cpi", datetime(2026, 8, 1))], _NOW, months=3.0)  # noqa: DTZ001
    assert dep
    assert dep[0]["event_type"] == "cn_cpi"


def test_depleting_override_forces_trigger():
    """★验证手段:阈值调大 → 远期种子也立即触发(手动 call months_override=24)。"""
    seeds = [("ecb", datetime(2027, 12, 16, tzinfo=UTC))]
    assert not seed_alert.depleting(seeds, _NOW, months=3.0)      # 默认 3 月不触发
    assert seed_alert.depleting(seeds, _NOW, months=24.0)         # 24 月阈值 → 触发


# ── 告警 + 去抖(mock redis/telegram)─────────────────────────────────────


class _FakeRedis:
    """set(nx=True) 首次 True(未发过)· 之后 None(去抖命中)。"""

    def __init__(self) -> None:
        self.calls = 0

    async def set(self, *args: object, **kwargs: object) -> bool | None:  # noqa: ARG002
        self.calls += 1
        return True if self.calls == 1 else None


@pytest.mark.asyncio
async def test_maybe_alert_sends_then_debounces(monkeypatch) -> None:  # noqa: ANN001
    sent: list[str] = []

    async def _fake_send(token: str, chat: str, text: str) -> None:  # noqa: ARG001
        sent.append(text)

    monkeypatch.setattr(seed_alert.settings, "tg_bot_token", "TOKEN")
    monkeypatch.setattr(seed_alert.settings, "admin_tg_chat_id", "CHAT")
    monkeypatch.setattr(seed_alert.telegram, "send", _fake_send)
    item = {"event_type": "cn_gdp", "latest": _NOW, "months_left": 1.7}
    redis = _FakeRedis()

    assert await seed_alert.maybe_alert(item, redis) is True     # 首发
    assert len(sent) == 1
    assert "种子枯竭告警" in sent[0]
    assert "cn_gdp" in sent[0]
    assert "rules.py" in sent[0]                                 # 可操作:指明补哪
    assert await seed_alert.maybe_alert(item, redis) is False    # 去抖 → 不重发
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_maybe_alert_no_tg_config_no_crash(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(seed_alert.settings, "tg_bot_token", "")
    monkeypatch.setattr(seed_alert.settings, "admin_tg_chat_id", "")
    redis = _FakeRedis()
    item = {"event_type": "cn_gdp", "latest": _NOW, "months_left": 1.0}
    assert await seed_alert.maybe_alert(item, redis) is False
    assert redis.calls == 0                                      # 未配置直接返回,不碰 redis


# ── 存储(DB · CI 跑)· ★仅 source='seed',滚动源排除 ─────────────────────


@pytest.mark.asyncio
async def test_seed_max_dates_only_seeds_not_rolling(db_session) -> None:  # noqa: ANN001
    """🔴 覆盖范围:只查硬编码种子(source='seed'),抓取/滚动源(dsbb/kostat…)不纳入。"""
    from app.services.econ_calendar.store import upsert_events

    now = _NOW
    await upsert_events(db_session, [
        {"event_key": "boj-2026-09", "event_type": "boj", "title": "日央行BOJ利率决议",
         "markets": ["us", "crypto"], "importance": 1,
         "scheduled_at": now + timedelta(days=30), "time_confirmed": False, "source": "seed"},
        {"event_key": "boj-2026-12", "event_type": "boj", "title": "日央行BOJ利率决议",
         "markets": ["us", "crypto"], "importance": 1,
         "scheduled_at": now + timedelta(days=160), "time_confirmed": False, "source": "seed"},
        # 滚动源 → 绝不该被查出(自动滚动·永在未来·纳入会永假告警)
        {"event_key": "gbcpi-x", "event_type": "gb_cpi", "title": "英国CPI", "markets": ["eu"],
         "importance": 1, "scheduled_at": now + timedelta(days=400),
         "time_confirmed": False, "source": "dsbb"},
        {"event_key": "krcpi-x", "event_type": "kr_cpi", "title": "韩国CPI", "markets": ["kr"],
         "importance": 1, "scheduled_at": now + timedelta(days=400),
         "time_confirmed": True, "source": "kostat"},
    ])
    db_session.expire_all()
    by = dict(await seed_alert.seed_max_dates(db_session))
    assert set(by) == {"boj"}                            # ★只种子 · 滚动源排除
    assert by["boj"] == now + timedelta(days=160)        # 取 max


@pytest.mark.asyncio
async def test_run_check_end_to_end(db_session, monkeypatch) -> None:  # noqa: ANN001
    """端到端:DB 查 → 筛快枯竭 → 告警(近期种子触发·远期不触发)。"""
    from app.services.econ_calendar.store import upsert_events

    now = _NOW
    await upsert_events(db_session, [
        {"event_key": "cn_gdp-2026-08", "event_type": "cn_gdp",
         "title": "中国季度GDP·国民经济运行发布会", "markets": ["cn", "hk"], "importance": 3,
         "scheduled_at": now + timedelta(days=40), "time_confirmed": True, "source": "seed"},
        {"event_key": "ecb-2027-12", "event_type": "ecb", "title": "欧央行ECB利率决议",
         "markets": ["us"], "importance": 1,
         "scheduled_at": now + timedelta(days=500), "time_confirmed": True, "source": "seed"},
    ])
    db_session.expire_all()
    sent: list[str] = []

    async def _send(token: str, chat: str, text: str) -> None:  # noqa: ARG001
        sent.append(text)

    monkeypatch.setattr(seed_alert.settings, "tg_bot_token", "TOKEN")
    monkeypatch.setattr(seed_alert.settings, "admin_tg_chat_id", "CHAT")
    monkeypatch.setattr(seed_alert.telegram, "send", _send)

    res: dict[str, Any] = await seed_alert.run_check(db_session, _FakeRedis(), now=now, months=3.0)
    assert res["ok"] is True
    assert res["checked"] == 2
    assert {d["event_type"] for d in res["depleting"]} == {"cn_gdp"}  # 只 cn_gdp 快枯竭
    assert res["depleting"][0]["alerted"] is True
    assert len(sent) == 1
    assert "cn_gdp" in sent[0]
