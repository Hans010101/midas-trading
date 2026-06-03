"""告警降噪 N1 测试矩阵 · 0028 N1。

🔴 红线:本期【只动去重层 + quiet 拦截】· 测试覆盖的是"什么时候推",
   evaluate_rule / 行情数据 / 推送链路本身不在本测试范围。

覆盖:
- quiet helper 纯函数(跨夜窗口 / 边界小时 / 时区)
- is_quiet_exempt:TradeFilledEvent 豁免、AlertTriggered/PriceAnomaly 不豁免
- dispatcher quiet 拦截 + dropped_quiet 信号 + 紧急豁免
- edge-triggered 状态机:持续 triggered 只推 1 次 / 离开复位 / 再进入再推 /
  cooldown 护栏 / dispatch 失败重试 / quiet 拦截写 state 防空转
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.services.notifications.dispatcher import dispatch
from app.services.notifications.events import (
    AlertTriggeredEvent,
    PriceAnomalyEvent,
    TradeFilledEvent,
)
from app.services.notifications.quiet import (
    _hour_in_quiet_window,
    is_in_quiet_now,
    is_quiet_exempt,
)
from tests.factories import make_user

# ============================================================================
# 纯函数 · _hour_in_quiet_window 跨夜 / 边界
# ============================================================================


def test_quiet_window_normal():
    """非跨夜:1–7 表示 [1, 7),边界 1 含 / 7 不含。"""
    assert _hour_in_quiet_window(1, 1, 7) is True
    assert _hour_in_quiet_window(3, 1, 7) is True
    assert _hour_in_quiet_window(6, 1, 7) is True
    assert _hour_in_quiet_window(7, 1, 7) is False  # 7 已不在窗口
    assert _hour_in_quiet_window(0, 1, 7) is False
    assert _hour_in_quiet_window(8, 1, 7) is False


def test_quiet_window_overnight():
    """跨夜:23–7 表示 hour ≥ 23 或 hour < 7(DP4 默认配置)。"""
    assert _hour_in_quiet_window(23, 23, 7) is True
    assert _hour_in_quiet_window(0, 23, 7) is True
    assert _hour_in_quiet_window(3, 23, 7) is True
    assert _hour_in_quiet_window(6, 23, 7) is True
    assert _hour_in_quiet_window(7, 23, 7) is False  # 7 出窗口
    assert _hour_in_quiet_window(22, 23, 7) is False  # 22 还没到
    assert _hour_in_quiet_window(12, 23, 7) is False


def test_quiet_window_disabled_when_equal():
    """start == end 视为禁用(永不在)· 让用户用 enabled=False 关。"""
    assert _hour_in_quiet_window(0, 0, 0) is False
    assert _hour_in_quiet_window(5, 5, 5) is False


# ============================================================================
# is_in_quiet_now · 时区 + enabled 开关
# ============================================================================


def _cfg(
    *, enabled: bool = True, start: int = 23, end: int = 7,
    tz: str = "Asia/Shanghai",
) -> NotificationConfig:
    """造一个 NotificationConfig(不入库 · 纯属性读)。"""
    return NotificationConfig(
        user_id=uuid4(), tg_chat_id=None,
        trade_alert_enabled=True, price_alert_enabled=True,
        quiet_hours_enabled=enabled,
        quiet_hours_start=start, quiet_hours_end=end,
        quiet_hours_tz=tz,
    )


def test_is_in_quiet_now_disabled():
    """quiet_hours_enabled=False → 始终 False(不论当前时间)。"""
    cfg = _cfg(enabled=False)
    assert is_in_quiet_now(cfg, datetime(2026, 1, 1, 3, 0, tzinfo=UTC)) is False
    assert is_in_quiet_now(cfg, datetime(2026, 1, 1, 15, 0, tzinfo=UTC)) is False


def test_is_in_quiet_now_none_config():
    """config=None(未注册过 notification)→ 总是 False。"""
    assert is_in_quiet_now(None, datetime(2026, 1, 1, 3, 0, tzinfo=UTC)) is False


def test_is_in_quiet_now_default_23_7_asia_shanghai():
    """DP4 默认 23–7 / Asia/Shanghai · UTC 19:00 对应 SH 03:00 → 应在 quiet。"""
    cfg = _cfg()  # 默认
    # UTC 19:00 = Asia/Shanghai 03:00 → 在窗口
    assert is_in_quiet_now(cfg, datetime(2026, 1, 1, 19, 0, tzinfo=UTC)) is True
    # UTC 06:00 = Asia/Shanghai 14:00 → 不在窗口
    assert is_in_quiet_now(cfg, datetime(2026, 1, 1, 6, 0, tzinfo=UTC)) is False
    # UTC 14:59 = Asia/Shanghai 22:59 → 不在窗口(22 还没到 23)
    assert is_in_quiet_now(cfg, datetime(2026, 1, 1, 14, 59, tzinfo=UTC)) is False
    # UTC 15:00 = Asia/Shanghai 23:00 → 在窗口(从 23 开始)
    assert is_in_quiet_now(cfg, datetime(2026, 1, 1, 15, 0, tzinfo=UTC)) is True


# ============================================================================
# is_quiet_exempt · 紧急豁免(DP10)
# ============================================================================


def test_is_quiet_exempt_trade_filled():
    """TradeFilledEvent = 钱相关 = 豁免(夜间也发)。"""
    evt = TradeFilledEvent(symbol="BTC", market="crypto")
    assert is_quiet_exempt(evt) is True


def test_is_quiet_exempt_alert_and_price_anomaly_not_exempt():
    """普通市场告警 = 非豁免(quiet 内被吞)。"""
    assert is_quiet_exempt(AlertTriggeredEvent()) is False
    assert is_quiet_exempt(PriceAnomalyEvent()) is False


# ============================================================================
# dispatcher · quiet 拦截 + dropped_quiet 信号 + 紧急豁免
# ============================================================================


@pytest.mark.asyncio
async def test_dispatch_quiet_drops_alert(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """quiet 时段 + AlertTriggeredEvent(非豁免)→ 不发 + dropped_quiet=True。

    ★ 确定化:monkeypatch is_in_quiet_now→True(不依赖运行时 wall-clock · 否则跨 CI run 时刻
    不同会 flaky)· 本测验的是「quiet=True 时 dispatch 丢弃告警」的 dispatch 行为;quiet 窗口
    边界([start,end) 端点排他)已由 is_in_quiet_now 注入-now 单测覆盖,此处不重复测边界。
    """
    user = await make_user(db_session)
    db_session.add(NotificationConfig(
        user_id=user.id, tg_chat_id="123",  # 已绑(但不应真发)
        quiet_hours_enabled=True, quiet_hours_start=0, quiet_hours_end=23,
        quiet_hours_tz="UTC",
    ))
    await db_session.commit()
    # 确定化 quiet=True(dispatch 默认用真实 wall-clock · 不注入 now → 不 stub 会时间依赖 flaky)
    monkeypatch.setattr(
        "app.services.notifications.dispatcher.is_in_quiet_now", lambda *_a, **_k: True,
    )

    evt = AlertTriggeredEvent(
        market="crypto", symbol="BTC/USDT", indicator_label="RSI",
        operator="gt", threshold=70.0, value=80.0,
    )
    result = await dispatch(db_session, user.id, evt)
    assert result.any_sent is False
    assert result.dropped_quiet is True
    assert result.results == []


@pytest.mark.asyncio
async def test_dispatch_quiet_does_not_drop_trade_filled(db_session: AsyncSession):
    """🔴 quiet 时段 + TradeFilledEvent(豁免)→ 照常派发(钱相关不漏 · DP10)。

    用 monkeypatch tg_adapter.send_event 验证 adapter 被调到(=进入派发阶段),
    且 dropped_quiet=False。
    """
    user = await make_user(db_session)
    db_session.add(NotificationConfig(
        user_id=user.id, tg_chat_id="123",
        quiet_hours_enabled=True, quiet_hours_start=0, quiet_hours_end=23,  # 全天 quiet
        quiet_hours_tz="UTC",
    ))
    await db_session.commit()

    evt = TradeFilledEvent(
        symbol="BTCUSDT", market="crypto", side="buy",
        quantity=Decimal("1"), price=Decimal("30000"),
        notional=Decimal("30000"), commission=Decimal("15"),
    )
    with patch(
        "app.services.notifications.dispatcher.tg_adapter.send_event",
        new=AsyncMock(),
    ) as mock_send, patch(
        "app.services.notifications.dispatcher.settings.tg_bot_token", "fake-token",
    ):
        result = await dispatch(db_session, user.id, evt)

    assert result.any_sent is True       # adapter 被成功调
    assert result.dropped_quiet is False  # quiet 没拦
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_outside_quiet_sends_alert(db_session: AsyncSession):
    """非 quiet 时段 + AlertTriggeredEvent → 正常派发。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(
        user_id=user.id, tg_chat_id="123",
        quiet_hours_enabled=False,  # 关 quiet
    ))
    await db_session.commit()

    evt = AlertTriggeredEvent(
        market="crypto", symbol="BTC/USDT", indicator_label="RSI",
        operator="gt", threshold=70.0, value=80.0,
    )
    with patch(
        "app.services.notifications.dispatcher.tg_adapter.send_event",
        new=AsyncMock(),
    ), patch(
        "app.services.notifications.dispatcher.settings.tg_bot_token", "fake-token",
    ):
        result = await dispatch(db_session, user.id, evt)

    assert result.any_sent is True
    assert result.dropped_quiet is False


# ============================================================================
# 边沿触发状态机 · 用 fake redis + 复刻 alert_scan 内的状态机片段
# ============================================================================


class _FakeRedis:
    """worker 用 redis 的最小子集 · 支持 set/get/del/expire(只为测状态机)。"""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._d.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:  # noqa: ARG002
        self._d[key] = value
        # ex 略 · 测试不模拟 TTL 真实流逝(用 redis.delete 模拟到期)

    async def delete(self, key: str) -> None:
        self._d.pop(key, None)


async def _edge_step(
    redis: _FakeRedis, rule_id: int, *, triggered: bool,
    sent: bool = True, dropped_quiet: bool = False,
    cooldown_sec: int = 300,
) -> str:
    """模拟一次 alert_scan 的状态机执行,返回该 step 的结果标签:
    'reset' / 'noop' / 'edge_sent' / 'edge_cooldown_block' / 'edge_quiet'。

    严格复刻 alert_scan.py 的状态机逻辑(便于在测试里逐 step 验证)。
    """
    curr = "triggered" if triggered else "not_triggered"
    state_key = f"alert_rule:state:{rule_id}"
    cool_key = f"alert_rule:cool:{rule_id}"
    prev = await redis.get(state_key)

    # 状态复位
    if prev == "triggered" and curr == "not_triggered":
        await redis.set(state_key, "not_triggered")
        return "reset"
    # 持续态
    if curr != "triggered" or prev == "triggered":
        return "noop"
    # edge fire 候选 · 看 cooldown
    if await redis.get(cool_key):
        return "edge_cooldown_block"
    # 派发(测试通过 sent/dropped_quiet 参数模拟 disp 结果)
    if sent:
        await redis.set(state_key, "triggered")
        await redis.set(cool_key, "1", ex=cooldown_sec)
        return "edge_sent"
    if dropped_quiet:
        await redis.set(state_key, "triggered")  # quiet:写 state 防空转
        return "edge_quiet"
    # dispatch 失败:不写 state · 下次重试
    return "edge_failed"


@pytest.mark.asyncio
async def test_edge_continuous_triggered_fires_once():
    """🔴 持续 triggered 5 轮 → 只 edge_sent 1 次,后 4 轮 noop。"""
    redis = _FakeRedis()
    results = [await _edge_step(redis, 1, triggered=True) for _ in range(5)]
    assert results == ["edge_sent", "noop", "noop", "noop", "noop"]


@pytest.mark.asyncio
async def test_edge_reset_then_reenter_fires_again():
    """🔴 进入 → 离开 → 再进入:推 2 次(2 个 edge)。"""
    redis = _FakeRedis()
    r1 = await _edge_step(redis, 1, triggered=True)   # edge_sent
    r2 = await _edge_step(redis, 1, triggered=True)   # noop
    # 模拟 cool key 到期(测试用 delete)
    await redis.delete("alert_rule:cool:1")
    r3 = await _edge_step(redis, 1, triggered=False)  # reset
    r4 = await _edge_step(redis, 1, triggered=True)   # edge_sent 又一次
    assert r1 == "edge_sent"
    assert r2 == "noop"
    assert r3 == "reset"
    assert r4 == "edge_sent"


@pytest.mark.asyncio
async def test_edge_cooldown_guards_flapping():
    """edge fire 后 cooldown 内即使重新 edge(离开+进入)也被压住。"""
    redis = _FakeRedis()
    r1 = await _edge_step(redis, 1, triggered=True)   # edge_sent · cool 写
    r2 = await _edge_step(redis, 1, triggered=False)  # reset
    r3 = await _edge_step(redis, 1, triggered=True)   # edge fire 候选 · 但 cool 还在 → block
    assert r1 == "edge_sent"
    assert r2 == "reset"
    assert r3 == "edge_cooldown_block"


@pytest.mark.asyncio
async def test_edge_dispatch_failure_retries_next_round():
    """dispatch 失败(非 quiet)→ state 不写 · 下次扫仍 edge fire。"""
    redis = _FakeRedis()
    r1 = await _edge_step(redis, 1, triggered=True, sent=False)  # edge_failed
    r2 = await _edge_step(redis, 1, triggered=True)  # 再 edge fire(因 state 仍 not_triggered)
    assert r1 == "edge_failed"
    assert r2 == "edge_sent"


@pytest.mark.asyncio
async def test_edge_quiet_writes_state_no_busy_loop():
    """🔴 quiet 拦截 → 写 state=triggered 防止下轮再判为 edge 空转 dispatcher。"""
    redis = _FakeRedis()
    r1 = await _edge_step(redis, 1, triggered=True, sent=False, dropped_quiet=True)
    r2 = await _edge_step(redis, 1, triggered=True)  # state 已 triggered → noop
    assert r1 == "edge_quiet"
    assert r2 == "noop"
