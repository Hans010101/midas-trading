"""做T 交易对 deep-link(feat/dot-t-coin-deeplink)单测。

覆盖:coin_deep_link 生成/回退 · handle_start coin_ 分流不碰 token · ★现有绑定 token 没破 ·
router /start coin_<SYM> → _quote_or_lite 出卡 · 三种消息 username 配后是 t.me 深链格式。
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.schemas.market import Kline
from app.services.ai.boll_state import (
    BollSnapshot,
    BollState,
    build_session_message,
    build_transition_digest,
    classify,
    render_card,
    state_label,
)
from app.services.clickhouse_client import ClickHouseClient
from app.services.notifications.telegram_bind import (
    COIN_PARAM_PREFIX,
    coin_deep_link,
    handle_start,
)

_BOT = "MidasTradeBot"


def _snap() -> BollSnapshot:
    kl = [
        Kline(ts=dt.datetime(2026, 6, 25, tzinfo=dt.UTC),
              open=100 + i, high=101 + i, low=99 + i, close=100.5 + i, volume=1000.0)
        for i in range(28)
    ]
    snap = classify(kl)
    assert snap is not None
    return snap


# ── coin_deep_link 生成 / 回退 ───────────────────────────────────────────

def test_coin_deep_link_username_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tg_bot_username", _BOT)
    assert coin_deep_link("BTCUSDT") == f"https://t.me/{_BOT}?start=coin_BTCUSDT"
    assert coin_deep_link("opnusdt") == f"https://t.me/{_BOT}?start=coin_OPNUSDT"  # 大写归一


def test_coin_deep_link_username_unset_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # ★未配 → None(调用方回退网页 · 链接不坏)
    monkeypatch.setattr(settings, "tg_bot_username", "")
    assert coin_deep_link("BTCUSDT") is None


def test_coin_param_prefix_value() -> None:
    assert COIN_PARAM_PREFIX == "coin_"


# ── handle_start:coin_ 分流 vs 绑定 token(★现有逻辑没破)───────────────────

@pytest.mark.asyncio
async def test_handle_start_coin_param_ignored_not_token() -> None:
    # ★/start coin_<SYM> → ignored(放行 router)· 绝不查/消耗绑定 token(redis 不被调)
    redis = AsyncMock()
    res = await handle_start(AsyncMock(), redis, chat_id=1, text="/start coin_BTCUSDT")
    assert res.kind == "ignored"
    redis.get.assert_not_called()        # 没走 peek_bind_token
    redis.delete.assert_not_called()     # 没 consume


@pytest.mark.asyncio
async def test_handle_start_invalid_token_still_rejected() -> None:
    # ★现有绑定没破:非 coin_ 的无效 token 仍报「无效」(peek 落空)
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    res = await handle_start(AsyncMock(), redis, chat_id=1, text="/start someRealLookingToken")
    assert res.kind == "invalid_token"
    redis.get.assert_awaited()  # 确实走了 token 校验路径(未被 coin_ 分流误吞)


@pytest.mark.asyncio
async def test_handle_start_bare_ignored() -> None:
    # 裸 /start(无 param)仍 ignored → 走主菜单(transport 既有)
    res = await handle_start(AsyncMock(), AsyncMock(), chat_id=1, text="/start")
    assert res.kind == "ignored"


# ── router:/start coin_<SYM> → _quote_or_lite("crypto", SYM)出行情卡 ───────

@pytest.mark.asyncio
async def test_router_coin_deeplink_routes_to_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.bot import router

    monkeypatch.setattr("app.services.bot.ratelimit.allow_command", AsyncMock(return_value=True))
    monkeypatch.setattr(router, "resolve_user_id", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(router, "clear_session", AsyncMock())
    captured: dict[str, tuple[str, str]] = {}

    async def fake_quote(_ch: object, market: str, symbol: str) -> str:
        captured["args"] = (market, symbol)
        return "CARD"

    monkeypatch.setattr(router, "_quote_or_lite", fake_quote)
    out = await router._handle_text(
        AsyncMock(), AsyncMock(), cast("ClickHouseClient", object()),
        "telegram", "123", "/start coin_BTCUSDT",
    )
    # ★深链 → 复用 _quote_or_lite(market 固定 crypto · symbol 大写)→ 出行情卡(不被绑定拦)
    assert captured["args"] == ("crypto", "BTCUSDT")
    assert len(out) == 1  # _quote_or_lite 的单卡结果原样作为唯一回复


# ── 三种消息 username 配后 = t.me 深链格式 ──────────────────────────────────

def test_three_messages_use_coin_deeplink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tg_bot_username", _BOT)
    from app.services.ai.boll_digest import build_hourly_digest

    link = f"https://t.me/{_BOT}?start=coin_BTCUSDT"
    snap = _snap()
    # ① 全景
    digest = build_hourly_digest(
        [{"symbol": "BTCUSDT", "bias": "偏多", "pct_b": 0.92,
          "state_label": "三线齐上·上升结构", "zone_label": "近上轨", "change_pct_24h": 5.0}],
        as_of_label="14:00",
    )
    assert digest is not None
    assert f"[BTCUSDT]({link})" in digest
    # ② 单转换方案B卡
    card_msg = build_session_message(
        [render_card("BTCUSDT", snap, transition_from=state_label(BollState.RANGE))],
    )
    assert f"[BTCUSDT]({link})" in card_msg
    # ③ 多转换合并
    multi = build_transition_digest([
        ("BTCUSDT", snap, state_label(BollState.RANGE)),
        ("ETHUSDT", snap, state_label(BollState.RANGE)),
    ])
    assert f"[BTCUSDT]({link})" in multi
