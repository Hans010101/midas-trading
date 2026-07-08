"""X 营销发布层(发布层 PR-1)单测:dispatch store / rate_limit / run_publish。

store/run = DB 测(midas_test · CI)· rate = FakeRedis 纯逻辑。
覆盖:幂等 upsert(reset-to-pending)· 频率守卫(日额/间隔)· run_publish 成功(mock 传输)+ ★门禁双保险。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.models.x_tweet import XTweet
from app.services.x_marketing.publish import rate_limit
from app.services.x_marketing.publish.dispatch import run_publish
from app.services.x_marketing.publish.store import (
    get_dispatch,
    list_dispatches,
    update_dispatch_result,
    upsert_pending,
)


class _FakeRedis:
    """最小异步 redis(get/set/incr/expire)· rate_limit/run_publish 测用,不连真 redis。"""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.store.get(k)

    async def set(self, k: str, v: Any) -> None:
        self.store[k] = v

    async def incr(self, k: str) -> int:
        self.store[k] = int(self.store.get(k, 0)) + 1
        return self.store[k]

    async def expire(self, k: str, ttl: int) -> None:
        pass


async def _mk_tweet(
    session: Any, *, passed: bool = True, auto_drafted: bool = False,
) -> XTweet:
    row = XTweet(
        symbol="BTCUSDT", bias="偏多", tweet_text="x 仅供参考",
        compliance_passed=passed, auto_drafted=auto_drafted,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# ── dispatch store(幂等)──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_pending_idempotent(db_session) -> None:  # noqa: ANN001
    tweet = await _mk_tweet(db_session)
    d1 = await upsert_pending(db_session, tweet_id=tweet.id, platform="binance_square", dispatched_by=None)
    assert d1.status == "pending"
    # 标记失败后重发 → 同一行 reset 为 pending(不新建 · 幂等)
    await update_dispatch_result(db_session, d1.id, status="failed", error="boom")
    d2 = await upsert_pending(db_session, tweet_id=tweet.id, platform="binance_square", dispatched_by=None)
    assert d2.id == d1.id  # ★同一行
    assert d2.status == "pending"
    assert d2.error is None  # reset 清了 error
    assert len(await list_dispatches(db_session, tweet.id)) == 1  # 仍只一条


@pytest.mark.asyncio
async def test_upsert_source_default_manual_and_auto(db_session) -> None:  # noqa: ANN001
    # ★source:默认 manual(兼容现有手动发)· 自动托管传 auto
    tweet = await _mk_tweet(db_session)
    d1 = await upsert_pending(db_session, tweet_id=tweet.id, platform="binance_square", dispatched_by=None)
    assert d1.source == "manual"  # 默认
    t2 = await _mk_tweet(db_session)
    d2 = await upsert_pending(
        db_session, tweet_id=t2.id, platform="binance_square", dispatched_by=None, source="auto",
    )
    assert d2.source == "auto"


@pytest.mark.asyncio
async def test_update_dispatch_result_success(db_session) -> None:  # noqa: ANN001
    tweet = await _mk_tweet(db_session)
    d = await upsert_pending(db_session, tweet_id=tweet.id, platform="binance_square", dispatched_by=None)
    await update_dispatch_result(
        db_session, d.id, status="success", platform_post_id="p1", url="https://x/p1",
    )
    got = await get_dispatch(db_session, tweet.id, "binance_square")
    assert got is not None
    assert got.status == "success"
    assert got.platform_post_url == "https://x/p1"


# ── rate_limit(频率守卫 · FakeRedis)──────────────────────────────────


@pytest.mark.asyncio
async def test_rate_daily_cap() -> None:
    r = _FakeRedis()
    # 把币安日计数顶到 100 → 拒绝
    r.store[rate_limit._daily_key("binance_square")] = 100
    ok, reason = await rate_limit.check_rate(r, "binance_square")
    assert ok is False
    assert "上限" in reason


@pytest.mark.asyncio
async def test_rate_min_interval() -> None:
    import time
    r = _FakeRedis()
    r.store[rate_limit._last_key("binance_square")] = str(time.time())  # 刚发过
    ok, reason = await rate_limit.check_rate(r, "binance_square")
    assert ok is False
    assert "频繁" in reason


@pytest.mark.asyncio
async def test_rate_record_post_increments() -> None:
    r = _FakeRedis()
    await rate_limit.record_post(r, "binance_square")
    assert int(r.store[rate_limit._daily_key("binance_square")]) == 1
    assert rate_limit._last_key("binance_square") in r.store  # 记了最近发帖时间


# ── run_publish(worker 核心 · stub 成功 + ★门禁双保险)──────────────────


@pytest.mark.asyncio
async def test_run_publish_success(db_session, monkeypatch) -> None:  # noqa: ANN001
    # 币安 adapter enabled 需 key → 给个测试 key
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "test-key")
    # ★PR-2:adapter 已是真 API → mock 传输层 _post_content(不打真 binance · 不依赖网络)
    from app.services.x_marketing.publish import binance_square as bs

    async def fake_post(text: str, image_urls: list[str] | None = None) -> dict[str, Any]:  # noqa: ARG001
        return {"code": "000000", "success": True, "data": {"id": "p1"}}

    monkeypatch.setattr(bs, "_post_content", fake_post)
    tweet = await _mk_tweet(db_session, passed=True)
    d = await upsert_pending(db_session, tweet_id=tweet.id, platform="binance_square", dispatched_by=None)
    result = await run_publish(db_session, _FakeRedis(), d.id)
    assert result["status"] == "success"
    got = await get_dispatch(db_session, tweet.id, "binance_square")
    assert got.status == "success"
    assert got.platform_post_id == "p1"  # 真 adapter 从响应 data.id 提取


@pytest.mark.asyncio
async def test_run_publish_auto_drafted_increments_daily(db_session, monkeypatch) -> None:  # noqa: ANN001
    # ★配额"算":auto_drafted 推文成功发布 → 计入 x:auto:daily_count(自动发 + 人工补发共用 · 单点)
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "test-key")
    from app.services.x_marketing.publish import auto_guard
    from app.services.x_marketing.publish import binance_square as bs

    async def fake_post(text: str, image_urls: list[str] | None = None) -> dict[str, Any]:  # noqa: ARG001
        return {"code": "000000", "success": True, "data": {"id": "p1"}}

    monkeypatch.setattr(bs, "_post_content", fake_post)
    r = _FakeRedis()
    # 普通推文(auto_drafted=False)→ 不计入自动配额
    plain = await _mk_tweet(db_session, passed=True, auto_drafted=False)
    dp = await upsert_pending(db_session, tweet_id=plain.id, platform="binance_square", dispatched_by=None)
    await run_publish(db_session, r, dp.id)
    assert await auto_guard.daily_remaining(r) == auto_guard.AUTO_DAILY_MAX  # 没动

    # auto_drafted 推文 → +1
    auto = await _mk_tweet(db_session, passed=True, auto_drafted=True)
    auto.symbol = "ETHUSDT"
    await db_session.commit()
    da = await upsert_pending(db_session, tweet_id=auto.id, platform="binance_square", dispatched_by=None)
    result = await run_publish(db_session, r, da.id)
    assert result["status"] == "success"
    assert await auto_guard.daily_remaining(r) == auto_guard.AUTO_DAILY_MAX - 1  # ★计入配额


@pytest.mark.asyncio
async def test_run_publish_auto_drafted_to_x_keeps_binance_quota(db_session, monkeypatch) -> None:  # noqa: ANN001
    """★step1 修复:auto_drafted 的 x_short 发到 X → 绝不 incr 币安 daily_count(独立配额·不挤占)。"""
    from app.core.config import settings
    from app.services.x_marketing.publish import auto_guard
    from app.services.x_marketing.publish import x_twitter as xt

    for k, v in (
        ("x_consumer_key", "ck"), ("x_consumer_secret", "cs"),
        ("x_access_token", "at"), ("x_access_token_secret", "ats"),
    ):
        monkeypatch.setattr(settings, k, v, raising=False)

    class _Resp:
        data = {"id": "x1"}

    monkeypatch.setattr(xt.XTwitterAdapter, "_post_sync", lambda *_: _Resp())  # mock X 发布成功
    r = _FakeRedis()
    auto = await _mk_tweet(db_session, passed=True, auto_drafted=True)  # 短文 "x 仅供参考" · X 不超限
    dp = await upsert_pending(db_session, tweet_id=auto.id, platform="x", dispatched_by=None)
    result = await run_publish(db_session, r, dp.id)
    assert result["status"] == "success"
    # ★发到 X 成功,但币安自动托管日配额【纹丝不动】(平台隔离·x_short 不挤占币安 30/日)
    assert await auto_guard.daily_remaining(r) == auto_guard.AUTO_DAILY_MAX


@pytest.mark.asyncio
async def test_run_publish_blocks_non_compliant(db_session, monkeypatch) -> None:  # noqa: ANN001
    # ★worker 侧双保险:门禁未过的,即使有 dispatch 也拒发(标 failed)
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "test-key")
    tweet = await _mk_tweet(db_session, passed=False)  # 门禁未过
    d = await upsert_pending(db_session, tweet_id=tweet.id, platform="binance_square", dispatched_by=None)
    result = await run_publish(db_session, _FakeRedis(), d.id)
    assert result["status"] == "failed"
    got = await get_dispatch(db_session, tweet.id, "binance_square")
    assert got.status == "failed"
    assert "门禁" in (got.error or "")
