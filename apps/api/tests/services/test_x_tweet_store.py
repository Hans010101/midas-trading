"""x_tweet 数据层(阶段4a · PR-1)单测:create(门禁不过也存)/ list_recent(24h)/ cleanup(删行+返图路径)。

DB 测(midas_test · CI 跑;本地无 PG 用 --collect-only 验证)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.platform_dispatch import PlatformDispatch
from app.models.x_tweet import XTweet
from app.services.x_marketing.store import (
    cleanup_expired,
    create_tweet,
    list_recent,
    set_image_path,
)


@pytest.mark.asyncio
async def test_create_stores_pass_and_fail(db_session) -> None:  # noqa: ANN001
    # ★门禁通过/不过都存(不过的记 reason · status 默认 draft)
    await create_tweet(
        db_session, symbol="BTCUSDT", bias="偏多",
        tweet_text="$BTC 偏多。仅供参考,不构成投资建议。\n#BTC #点金Midas",
        compliance_passed=True,
    )
    await create_tweet(
        db_session, symbol="ETHUSDT", bias="偏空", tweet_text="坏推文",
        compliance_passed=False, compliance_reason="预测未来走势词:即将突破",
    )
    rows = await list_recent(db_session)
    assert len(rows) == 2
    eth = next(r for r in rows if r.symbol == "ETHUSDT")
    assert eth.compliance_passed is False
    assert eth.compliance_reason == "预测未来走势词:即将突破"
    assert eth.status == "draft"  # ★止于待发


@pytest.mark.asyncio
async def test_list_recent_only_24h(db_session) -> None:  # noqa: ANN001
    now = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
    db_session.add_all([
        XTweet(symbol="OLDUSDT", bias="中性", tweet_text="老", compliance_passed=True,
               created_at=now - timedelta(hours=25)),
        XTweet(symbol="NEWUSDT", bias="偏多", tweet_text="新", compliance_passed=True,
               created_at=now - timedelta(hours=1)),
    ])
    await db_session.commit()
    rows = await list_recent(db_session, now=now)
    assert [r.symbol for r in rows] == ["NEWUSDT"]  # 只显 24h 内


@pytest.mark.asyncio
async def test_set_image_path(db_session) -> None:  # noqa: ANN001
    # x-shooter 截完 · 主 worker 回调更新 image_path
    row = await create_tweet(
        db_session, symbol="BTCUSDT", bias="偏多", tweet_text="x", compliance_passed=True,
    )
    ok = await set_image_path(db_session, row.id, "/shots/1.png")
    assert ok is True
    refreshed = await list_recent(db_session)
    assert refreshed[0].image_path == "/shots/1.png"
    # 行不存在 → False(截图回来但行已被 24h 清理)
    assert await set_image_path(db_session, 999999, "/shots/x.png") is False


@pytest.mark.asyncio
async def test_cleanup_deletes_old_and_returns_image_paths(db_session) -> None:  # noqa: ANN001
    now = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
    db_session.add_all([
        XTweet(symbol="OLDUSDT", bias="偏空", tweet_text="老", compliance_passed=True,
               image_path="/vol/x-shots/old.png", created_at=now - timedelta(hours=73)),
        XTweet(symbol="NEWUSDT", bias="偏多", tweet_text="新", compliance_passed=True,
               created_at=now - timedelta(hours=1)),
    ])
    await db_session.commit()
    paths = await cleanup_expired(db_session, now=now)
    assert paths == ["/vol/x-shots/old.png"]  # ★返回旧行图路径给 worker 删文件
    remaining = await list_recent(db_session, now=now)
    assert [r.symbol for r in remaining] == ["NEWUSDT"]  # 旧的(>72h)删了,新的留


@pytest.mark.asyncio
async def test_cleanup_skips_published(db_session) -> None:  # noqa: ANN001
    # ★发布层 PR-1:有 platform_dispatch 台账的推文(已发布)豁免 72h 清理(留审计)
    now = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
    pub = XTweet(symbol="PUBUSDT", bias="偏多", tweet_text="已发", compliance_passed=True,
                 image_path="/vol/x-shots/pub.png", created_at=now - timedelta(hours=100))
    plain = XTweet(symbol="OLDUSDT", bias="偏空", tweet_text="没发", compliance_passed=True,
                   created_at=now - timedelta(hours=100))
    db_session.add_all([pub, plain])
    await db_session.commit()
    db_session.add(PlatformDispatch(tweet_id=pub.id, platform="binance_square", status="success"))
    await db_session.commit()

    paths = await cleanup_expired(db_session, now=now)
    assert paths == []  # 没发的没图;已发的豁免不删 → 无图路径返回
    survivors = (await db_session.execute(select(XTweet.symbol))).scalars().all()
    assert "PUBUSDT" in survivors  # ★已发布的留着(审计)
    assert "OLDUSDT" not in survivors  # 没发的(>72h 无 dispatch)被清
