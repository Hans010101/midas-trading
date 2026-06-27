"""X 营销自动托管 · 自动发布编排(PR-3)单测:发布前守卫重检 + 成功记账 + 失败退避熔断。

DB(midas_test · CI · upsert_pending 真建 dispatch)+ FakeRedis + mock run_publish(不打币安)。
★退避护栏:连续 FAIL_THRESHOLD(3)次失败 → 开熔断 + circuit_opened=True。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from app.models.x_tweet import XTweet
from app.services.visit_stats import CN_TZ
from app.services.x_marketing import auto_publish as ap
from app.services.x_marketing.publish import auto_guard


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


def _in_window() -> datetime:
    return datetime(2026, 6, 27, 13, 0, tzinfo=CN_TZ)


async def _mk_tweet(session: Any, *, passed: bool = True) -> XTweet:
    row = XTweet(symbol="BTCUSDT", bias="偏多", tweet_text="x 仅供参考", compliance_passed=passed)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def _mock_publish(monkeypatch, status: str) -> None:  # noqa: ANN001
    async def fake(session: Any, redis: Any, dispatch_id: int) -> dict[str, Any]:  # noqa: ARG001
        if status == "success":
            return {"status": "success", "url": "https://binance/p1"}
        return {"status": "failed", "error": "boom"}
    monkeypatch.setattr(ap, "run_publish", fake)


async def _enabled_redis() -> _FakeRedis:
    r = _FakeRedis()
    await auto_guard.set_enabled(r, enabled=True)
    return r


# ── 发布前守卫重检 skip(紧急熔断兜底)──────────────────────────────────


@pytest.mark.asyncio
async def test_publish_skips_when_disabled(db_session) -> None:  # noqa: ANN001
    r = _FakeRedis()  # 开关 OFF
    out = await ap.run_auto_publish(db_session, r, tweet_id=1, symbol="BTCUSDT", now=_in_window())
    assert out == {"status": "skip", "reason": "disabled"}


@pytest.mark.asyncio
async def test_publish_skips_circuit_open(db_session) -> None:  # noqa: ANN001
    r = await _enabled_redis()
    await auto_guard.open_circuit(r)  # countdown 期间被紧急熔断
    out = await ap.run_auto_publish(db_session, r, tweet_id=1, symbol="BTCUSDT", now=_in_window())
    assert out["reason"] == "circuit_open"


@pytest.mark.asyncio
async def test_publish_skips_out_of_window(db_session) -> None:  # noqa: ANN001
    r = await _enabled_redis()
    out = await ap.run_auto_publish(
        db_session, r, tweet_id=1, symbol="BTCUSDT",
        now=datetime(2026, 6, 27, 23, 0, tzinfo=CN_TZ),  # 23:00 窗外
    )
    assert out["reason"] == "out_of_window"


@pytest.mark.asyncio
async def test_publish_skips_duplicate(db_session) -> None:  # noqa: ANN001
    r = await _enabled_redis()
    await auto_guard.mark_published(r, "BTCUSDT")  # 6h 内已发
    out = await ap.run_auto_publish(db_session, r, tweet_id=1, symbol="BTCUSDT", now=_in_window())
    assert out["reason"] == "duplicate"


# ── 成功记账:去重 + 日计数 + 清失败 ──────────────────────────────────


@pytest.mark.asyncio
async def test_publish_success_marks_and_counts(db_session, monkeypatch) -> None:  # noqa: ANN001
    _mock_publish(monkeypatch, "success")
    r = await _enabled_redis()
    await auto_guard.record_fail(r)  # 先有 1 次历史失败,成功后应清零
    tweet = await _mk_tweet(db_session, passed=True)
    out = await ap.run_auto_publish(
        db_session, r, tweet_id=tweet.id, symbol="BTCUSDT", now=_in_window(),
    )
    assert out["status"] == "success"
    assert await auto_guard.is_recently_published(r, "BTCUSDT") is True  # ★6h 去重已标
    assert await auto_guard.daily_remaining(r, _in_window()) == auto_guard.AUTO_DAILY_MAX - 1  # 计数+1
    assert await auto_guard.record_fail(r) == 1  # reset 后从 1 起(说明成功清了)


# ── 失败退避:连续失败计数,达阈值开熔断 ──────────────────────────────


@pytest.mark.asyncio
async def test_publish_fail_records_below_threshold(db_session, monkeypatch) -> None:  # noqa: ANN001
    _mock_publish(monkeypatch, "failed")
    r = await _enabled_redis()
    tweet = await _mk_tweet(db_session, passed=True)
    out = await ap.run_auto_publish(
        db_session, r, tweet_id=tweet.id, symbol="BTCUSDT", now=_in_window(),
    )
    assert out["status"] == "failed"
    assert out["fail_count"] == 1
    assert out["circuit_opened"] is False  # 未到阈值
    assert await auto_guard.is_circuit_open(r) is False


@pytest.mark.asyncio
async def test_publish_fail_threshold_opens_circuit(db_session, monkeypatch) -> None:  # noqa: ANN001
    _mock_publish(monkeypatch, "failed")
    r = await _enabled_redis()
    # 预置已连续失败 2 次 → 本次第 3 次触发熔断
    await auto_guard.record_fail(r)
    await auto_guard.record_fail(r)
    tweet = await _mk_tweet(db_session, passed=True)
    out = await ap.run_auto_publish(
        db_session, r, tweet_id=tweet.id, symbol="BTCUSDT", now=_in_window(),
    )
    assert out["fail_count"] == auto_guard.FAIL_THRESHOLD  # 3
    assert out["circuit_opened"] is True  # ★达阈值开熔断
    assert await auto_guard.is_circuit_open(r) is True  # 熔断真的开了 → 停所有自动发
