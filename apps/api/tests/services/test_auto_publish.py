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
async def test_publish_skips_after_delay_past_window(db_session) -> None:  # noqa: ANN001
    # ★边界2(时段 TOCTOU):起草 22:28 + 随机延迟 7min → 实际发布 22:35 → 守卫复检按【延迟后实际时刻】
    # → 22:35 > 22:30 → skip 不发。run_auto_publish 用执行时的真实时刻(worker 延迟后才跑 → now=实际)。
    r = await _enabled_redis()
    out = await ap.run_auto_publish(
        db_session, r, tweet_id=1, symbol="BTCUSDT",
        now=datetime(2026, 6, 27, 22, 35, tzinfo=CN_TZ),  # 延迟后超 22:30
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
    assert await auto_guard.record_fail(r) == 1  # reset 后从 1 起(说明成功清了)
    # ★日计数 +1 不在这测:已移到 run_publish(此处 run_publish 被 mock)· 配额 incr 见 test_x_publish


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


# ── 随机发布延迟(★1-7min · 抹固定分钟指纹 · 频率调整)────────────────


def test_publish_delay_in_range() -> None:
    # ★延迟 ∈ [60, 420](1-7min)· 多次抽样确认边界 · 非配速(每次随机)
    for _ in range(100):
        d = ap.publish_delay_seconds()
        assert 60 <= d <= 420


# ── ★架子刀(ADR 0050):平台勾选分闸 + 白名单物理锁 ─────────────────────


@pytest.mark.asyncio
async def test_resolve_platforms_whitelist_welds_x() -> None:
    """★★红线焊死:把 x 勾选强翻 ON(模拟配置层被绕),resolve 仍只可能返回白名单平台。

    X 不在 _AUTO_PUBLISH_ALLOWED → 无论 Redis 勾选值如何,自动路径永远拿不到 "x"。
    """
    r = _FakeRedis()
    await auto_guard.set_platform_checked(r, "x", checked=True)  # 强翻 X 勾选
    platforms = await ap.resolve_auto_platforms(r)
    assert "x" not in platforms                     # ★白名单物理锁:X 焊死
    assert platforms == ["binance_square"]          # binance 默认 ON 照常


@pytest.mark.asyncio
async def test_publish_skips_when_binance_unchecked(db_session) -> None:  # noqa: ANN001
    """★分闸:admin 取消勾选币安 → 自动发布 skip(总开关仍 ON·起草不受影响)。"""
    r = await _enabled_redis()
    await auto_guard.set_platform_checked(r, "binance_square", checked=False)
    tweet = await _mk_tweet(db_session, passed=True)
    out = await ap.run_auto_publish(
        db_session, r, tweet_id=tweet.id, symbol=tweet.symbol, now=_in_window(),
    )
    assert out == {"status": "skip", "reason": "no_platform_checked"}


@pytest.mark.asyncio
async def test_publish_default_unset_platform_still_publishes(db_session, monkeypatch) -> None:  # noqa: ANN001
    """★现状零变化:平台勾选键从未设置(存量部署)→ binance 默认 ON → 照常自动发。"""
    _mock_publish(monkeypatch, "success")
    r = await _enabled_redis()  # 无任何 platform 键
    tweet = await _mk_tweet(db_session, passed=True)
    out = await ap.run_auto_publish(
        db_session, r, tweet_id=tweet.id, symbol=tweet.symbol, now=_in_window(),
    )
    assert out["status"] == "success"  # 行为与旧 _PLATFORM 硬编码逐字节一致
