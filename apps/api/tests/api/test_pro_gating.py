"""变现强化:Pro 门控 + 可选身份依赖 + 月配额 · pytest。

覆盖:
- get_optional_current_user:有效 token→User · 无/坏 token→None(★不抛 401)。
- decision-card / strategy-signals 门控:
  · 非 Pro(免费登录 / 未登录)→ locked 空壳 + 【无真实内容】(防 F12)+ 【不触发 workflow/scan】(不烧 LLM/省算力)。
  · 未登录(user=None)→ locked 而非 401(不破坏访客访问详情页)。
  · Pro → 越过门控跑到 workflow/scan(sentinel 证明完整路径执行)。
- 配额改革:quota_key 按月(YYYYMM)· reset 下月 1 号(含跨年)· TTL ≥ 31 天。

🔴 红线:locked 响应绝不含真实 AI 决策内容;可选身份未登录不抛 401。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.v1.analysis as analysis_mod
from app.api.deps import get_optional_current_user
from app.api.v1.analysis import get_decision_card, get_strategy_signals
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.market import Kline
from app.services.auth import issue_session
from app.services.membership import _QUOTA_KEY_TTL_S, quota_key, quota_reset_at
from tests.factories import make_user

_TZ8 = timezone(timedelta(hours=8))
_MONTH_LEN = 6
_MIN_TTL_S = 31 * 24 * 3600


class _Sentinel(Exception):  # noqa: N818 — 测试哨兵,非真实错误,不用 Error 后缀
    """哨兵:被调用即抛 · 证明该计算点被(或未被)触达。"""


class _FakeCH:
    def __init__(self, klines: list[Kline]) -> None:
        self._klines = klines
        self._client = object()

    async def select_kline(self, **_kw: Any) -> list[Kline]:
        return list(self._klines)


def _kl(n: int = 35) -> list[Kline]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Kline(
            ts=start + timedelta(days=i), open=10.0, high=15.0, low=8.0,
            close=10.0 + (i % 3), volume=1000.0, amount=None,
        )
        for i in range(n)
    ]


async def _boom_workflow(*_a: Any, **_k: Any) -> Any:
    raise _Sentinel


def _boom_scan(*_a: Any, **_k: Any) -> Any:  # scan_signals 是同步调用
    raise _Sentinel


async def _none_cache(*_a: Any, **_k: Any) -> None:
    return None


async def _user_with_plan(db: AsyncSession, plan: str) -> User:
    user = await make_user(db)
    if plan == "pro":
        db.add(Subscription(user_id=user.id, plan="pro", status="active", source="manual"))
        await db.commit()
    return user


# ── 可选身份依赖 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_optional_user_valid_token_returns_user(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    got = await get_optional_current_user(token, db_session)
    assert got is not None
    assert got.id == user.id


@pytest.mark.asyncio
async def test_optional_user_no_token_returns_none(db_session: AsyncSession) -> None:
    """🔴 无 token → None(不抛 401 · 不破坏访客访问)。"""
    assert await get_optional_current_user(None, db_session) is None


@pytest.mark.asyncio
async def test_optional_user_bad_token_returns_none(db_session: AsyncSession) -> None:
    """🔴 无效 token → None(不抛 401)。"""
    assert await get_optional_current_user("garbage-not-a-session", db_session) is None


# ── decision-card 门控 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decision_card_free_locked_no_content(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 免费登录 → locked 空壳:无 score/解读/信号/actionable + 不触发 workflow(不烧 LLM)。"""
    monkeypatch.setattr(analysis_mod, "run_decision_workflow", _boom_workflow)
    user = await _user_with_plan(db_session, "free")
    resp = await get_decision_card(
        _FakeCH(_kl()), None, None, None, None, None, db_session, user, "zh",  # type: ignore[arg-type]
        symbol="NVDA", market="us", period="1d",
    )
    assert resp.locked is True
    assert resp.composite_score == 0
    assert resp.narrative == ""
    assert resp.chan_signals == []
    assert resp.actionable is None


@pytest.mark.asyncio
async def test_decision_card_anon_locked_no_401(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 未登录(user=None)→ locked,不抛 401(访客访问详情页不被破坏)。"""
    monkeypatch.setattr(analysis_mod, "run_decision_workflow", _boom_workflow)
    resp = await get_decision_card(
        _FakeCH(_kl()), None, None, None, None, None, db_session, None, "zh",  # type: ignore[arg-type]
        symbol="NVDA", market="us", period="1d",
    )
    assert resp.locked is True
    assert resp.composite_score == 0


@pytest.mark.asyncio
async def test_decision_card_pro_reaches_workflow(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pro → 越过门控跑到 workflow(sentinel)· 证明完整路径仅 Pro 执行(烧 LLM)。"""
    monkeypatch.setattr(analysis_mod, "get_cached_card", _none_cache)  # 强制 cache miss
    monkeypatch.setattr(analysis_mod, "run_decision_workflow", _boom_workflow)
    user = await _user_with_plan(db_session, "pro")
    with pytest.raises(_Sentinel):
        await get_decision_card(
            _FakeCH(_kl()), None, None, None, None, None, db_session, user, "zh",  # type: ignore[arg-type]
            symbol="NVDA", market="us", period="1d",
        )


# ── strategy-signals 门控 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_strategy_signals_free_locked_no_signals(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 免费登录 → locked 空壳:无 signals + 不触发 scan(省算力)。"""
    monkeypatch.setattr(analysis_mod, "scan_signals", _boom_scan)
    user = await _user_with_plan(db_session, "free")
    resp = await get_strategy_signals(
        _FakeCH(_kl()), None, None, None, None, None, db_session, user, "zh",  # type: ignore[arg-type]
        symbol="NVDA", market="us", period="1d", instrument="spot", strategy="ma_cross",
    )
    assert resp.locked is True
    assert resp.signals == []
    assert resp.current_triggered is False
    assert resp.last_signal is None


@pytest.mark.asyncio
async def test_strategy_signals_anon_locked_no_401(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 未登录 → locked,不抛 401。"""
    monkeypatch.setattr(analysis_mod, "scan_signals", _boom_scan)
    resp = await get_strategy_signals(
        _FakeCH(_kl()), None, None, None, None, None, db_session, None, "zh",  # type: ignore[arg-type]
        symbol="NVDA", market="us", period="1d", instrument="spot", strategy="ma_cross",
    )
    assert resp.locked is True
    assert resp.signals == []


@pytest.mark.asyncio
async def test_strategy_signals_pro_reaches_scan(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pro → 越过门控跑到 scan_signals(sentinel)· 证明完整路径仅 Pro 执行。"""
    monkeypatch.setattr(analysis_mod, "scan_signals", _boom_scan)
    user = await _user_with_plan(db_session, "pro")
    with pytest.raises(_Sentinel):
        await get_strategy_signals(
            _FakeCH(_kl()), None, None, None, None, None, db_session, user, "zh",  # type: ignore[arg-type]
            symbol="NVDA", market="us", period="1d", instrument="spot", strategy="ma_cross",
        )


# ── 配额改革:月 key / 下月 reset(跨年)/ TTL ──────────────────────────────────


def test_quota_key_is_monthly() -> None:
    uid = uuid4()
    key = quota_key(uid, "diagnose")
    month = datetime.now(_TZ8).strftime("%Y%m")
    assert key == f"quota:{uid}:diagnose:{month}"
    assert len(month) == _MONTH_LEN  # YYYYMM(非 YYYYMMDD)


def test_quota_reset_next_month_first() -> None:
    r = quota_reset_at(datetime(2026, 3, 15, 10, 30, tzinfo=_TZ8))
    assert (r.year, r.month, r.day, r.hour, r.minute) == (2026, 4, 1, 0, 0)


def test_quota_reset_year_rollover() -> None:
    """★ 跨年:12 月 → 次年 1 月 1 号。"""
    r = quota_reset_at(datetime(2026, 12, 20, 23, 0, tzinfo=_TZ8))
    assert (r.year, r.month, r.day, r.hour) == (2027, 1, 1, 0)


def test_quota_ttl_covers_full_month() -> None:
    """★ TTL ≥ 31 天(否则月内 key 提前过期 → 配额误重置)。"""
    assert _QUOTA_KEY_TTL_S >= _MIN_TTL_S
