"""Bot 安静时段 pytest · 0028 N3。

两层测试:
1. 核心层 quiet_mod 纯逻辑 · 跨用户隔离 / 小时步进边界 / lazy create / 不改其他字段
2. router e2e · 未绑定拒绝 / menu:quiet 渲染 / toggle 真翻 / 不污染下单&告警路径

🔴 重点:test_quiet_cross_user_isolation_A_cannot_affect_B(本期 review 必看)。
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.services.bot import quiet as quiet_mod
from app.services.bot import router
from tests.factories import make_user

# ── shared fakes(同 test_bot_router.py 模式 · 避免跨文件耦合) ────────────


class _FakeRedis:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self._d.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._d[key] = value

    async def delete(self, key: str) -> None:
        self._d.pop(key, None)

    async def incr(self, key: str) -> int:
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    async def expire(self, _key: str, _ttl: int) -> None:
        return None


class _FakeCH:
    def __init__(self) -> None:
        self._client = object()


async def _bind(db: AsyncSession, user_id: UUID, chat_id: int) -> None:
    db.add(NotificationConfig(user_id=user_id, tg_chat_id=str(chat_id)))
    await db.commit()


async def _read_config(db: AsyncSession, user_id: UUID) -> NotificationConfig | None:
    return await db.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user_id),
    )


# ══════════════════════════════════════════════════════════════════════
# 核心层 quiet_mod 单测
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_load_unconfigured_returns_default_view(db_session: AsyncSession):
    """未配置用户 load → 默认 view(23-7 / Asia/Shanghai / 启用)· 不 lazy create。"""
    user = await make_user(db_session)
    await db_session.commit()

    view = await quiet_mod.load_quiet_hours(db_session, user.id)
    assert view.enabled is True
    assert view.start_hour == 23
    assert view.end_hour == 7
    assert view.tz == "Asia/Shanghai"

    # 只读 · 不应 lazy create
    cfg = await _read_config(db_session, user.id)
    assert cfg is None


@pytest.mark.asyncio
async def test_toggle_lazy_creates_config_and_flips(db_session: AsyncSession):
    """toggle 在未配置时 lazy create · 写入入参 user_id · 翻 enabled。"""
    user = await make_user(db_session)
    await db_session.commit()

    view = await quiet_mod.toggle_enabled(db_session, user.id)
    # server_default enabled=true · toggle → false
    assert view.enabled is False

    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.user_id == user.id   # 🔴 写到入参 user_id 名下
    assert cfg.quiet_hours_enabled is False
    # 其他字段保持 server_default
    assert cfg.quiet_hours_start == 23
    assert cfg.quiet_hours_end == 7
    assert cfg.quiet_hours_tz == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_toggle_again_flips_back(db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()

    v1 = await quiet_mod.toggle_enabled(db_session, user.id)
    v2 = await quiet_mod.toggle_enabled(db_session, user.id)
    assert v1.enabled is False
    assert v2.enabled is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial", "delta", "expected"),
    [
        (23, +1, 0),   # 23 + 1 → 0(跨日回卷)
        (0, -1, 23),   # 0 - 1 → 23(回卷)
        (10, +1, 11),  # 普通 +1
        (10, -1, 9),   # 普通 -1
        (0, +1, 1),    # 普通边界
        (23, -1, 22),  # 普通边界
    ],
)
async def test_step_start_hour_wraps_at_boundary(
    db_session: AsyncSession, initial: int, delta: int, expected: int,
):
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, quiet_hours_start=initial))
    await db_session.commit()

    view = await quiet_mod.step_start_hour(db_session, user.id, delta)
    assert view.start_hour == expected
    # 不动 end / enabled / tz
    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.quiet_hours_start == expected
    assert cfg.quiet_hours_end == 7   # server_default 未动
    assert cfg.quiet_hours_tz == "Asia/Shanghai"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial", "delta", "expected"),
    [
        (23, +1, 0),
        (0, -1, 23),
        (7, +1, 8),
        (7, -1, 6),
    ],
)
async def test_step_end_hour_wraps_at_boundary(
    db_session: AsyncSession, initial: int, delta: int, expected: int,
):
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, quiet_hours_end=initial))
    await db_session.commit()

    view = await quiet_mod.step_end_hour(db_session, user.id, delta)
    assert view.end_hour == expected
    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.quiet_hours_end == expected


@pytest.mark.asyncio
async def test_step_doesnt_touch_other_fields(db_session: AsyncSession):
    """step 只动目标小时字段 · trade_alert / price_alert / tg_chat_id / tz 全不动。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(
        user_id=user.id,
        tg_chat_id="123",
        trade_alert_enabled=False,  # 跟 server_default 不同 · 测真不动
        price_alert_enabled=False,
        quiet_hours_enabled=False,
        quiet_hours_start=10,
        quiet_hours_end=20,
        quiet_hours_tz="UTC",
    ))
    await db_session.commit()

    await quiet_mod.step_start_hour(db_session, user.id, +1)

    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.quiet_hours_start == 11      # 只这个变
    assert cfg.tg_chat_id == "123"          # 不动
    assert cfg.trade_alert_enabled is False  # 不动
    assert cfg.price_alert_enabled is False  # 不动
    assert cfg.quiet_hours_enabled is False  # 不动
    assert cfg.quiet_hours_end == 20         # 不动
    assert cfg.quiet_hours_tz == "UTC"       # 不动


# ⭐⭐⭐ 跨用户隔离(本期 review 必看)─────────────────────────────────────
@pytest.mark.asyncio
async def test_cross_user_isolation_a_cannot_affect_b(db_session: AsyncSession):
    """🔴 R1 红线:对 user_A 的所有操作 · B 的 config 一字节不动。

    quiet_mod 模块层不接受 chat_id / 其他 id · user_id 是唯一入参 · 物理上
    不可能错位。本测试枚举三种操作(toggle / step start / step end),逐一
    验证 B 的 config 跟初始一致。
    """
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    # B 的 config 预置非默认值 · 任何意外写入都能被发现
    db_session.add(NotificationConfig(
        user_id=user_b.id,
        tg_chat_id="b-chat",
        quiet_hours_enabled=False,
        quiet_hours_start=10,
        quiet_hours_end=20,
        quiet_hours_tz="UTC",
    ))
    await db_session.commit()

    # 对 A 跑全套操作
    await quiet_mod.toggle_enabled(db_session, user_a.id)
    await quiet_mod.step_start_hour(db_session, user_a.id, +1)
    await quiet_mod.step_start_hour(db_session, user_a.id, -1)
    await quiet_mod.step_end_hour(db_session, user_a.id, +5)
    await quiet_mod.step_end_hour(db_session, user_a.id, -5)
    await quiet_mod.toggle_enabled(db_session, user_a.id)

    # B 一字节不动
    cfg_b = await _read_config(db_session, user_b.id)
    assert cfg_b is not None
    assert cfg_b.user_id == user_b.id
    assert cfg_b.tg_chat_id == "b-chat"
    assert cfg_b.quiet_hours_enabled is False
    assert cfg_b.quiet_hours_start == 10
    assert cfg_b.quiet_hours_end == 20
    assert cfg_b.quiet_hours_tz == "UTC"

    # A 的 config 应已建 + 翻转后 enabled 回到 True(2 次 toggle)
    cfg_a = await _read_config(db_session, user_a.id)
    assert cfg_a is not None
    assert cfg_a.user_id == user_a.id
    assert cfg_a.quiet_hours_enabled is True  # 2 次 toggle 回原状


# ══════════════════════════════════════════════════════════════════════
# router e2e
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_router_quiet_unbound_renders_not_bound(db_session: AsyncSession):
    """未绑定 chat 点 menu:quiet → render_not_bound · 拒绝操作。"""
    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 1234, "menu:quiet",  # type: ignore[arg-type]
    )
    assert "绑定" in reply.text
    # 未绑定 chat 不应 lazy create 任何 config
    cfg = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.tg_chat_id == "1234"),
    )
    assert cfg is None


@pytest.mark.asyncio
async def test_router_menu_quiet_shows_defaults_when_new(db_session: AsyncSession):
    """已绑定 chat 但没 quiet 配置 → 显示默认 23-7 / Asia/Shanghai / 启用。"""
    user = await make_user(db_session)
    # 注意:_bind 已经在 NotificationConfig 里创建 row · server_default 给 quiet_hours
    await _bind(db_session, user.id, 5001)

    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 5001, "menu:quiet",  # type: ignore[arg-type]
    )
    assert "安静时段" in reply.text
    assert "23:00" in reply.text  # start_hour 默认
    assert "Asia/Shanghai" in reply.text
    # 紧急豁免说明在
    assert "强平" in reply.text


@pytest.mark.asyncio
async def test_router_quiet_toggle_flips_and_renders(db_session: AsyncSession):
    """点 quiet:toggle → 翻 enabled + 重渲染。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 5002)

    r1 = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 5002, "quiet:toggle",  # type: ignore[arg-type]
    )
    # server_default enabled=True · 一次 toggle → False(关闭)· 状态文本 "已关闭"
    assert "已关闭" in r1.text

    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.quiet_hours_enabled is False


@pytest.mark.asyncio
async def test_router_quiet_step_callbacks(db_session: AsyncSession):
    """点 quiet:s+/s-/e+/e- · 逐项验证小时变化。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 5003)

    redis = _FakeRedis()
    ch = _FakeCH()

    # 默认 start=23,+1 应回卷到 0
    await router.handle_callback(db_session, redis, ch, 5003, "quiet:s+")  # type: ignore[arg-type]
    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.quiet_hours_start == 0

    # -1 应回到 23
    await router.handle_callback(db_session, redis, ch, 5003, "quiet:s-")  # type: ignore[arg-type]
    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.quiet_hours_start == 23

    # 默认 end=7,+1 → 8
    await router.handle_callback(db_session, redis, ch, 5003, "quiet:e+")  # type: ignore[arg-type]
    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.quiet_hours_end == 8

    # -1 → 7
    await router.handle_callback(db_session, redis, ch, 5003, "quiet:e-")  # type: ignore[arg-type]
    cfg = await _read_config(db_session, user.id)
    assert cfg is not None
    assert cfg.quiet_hours_end == 7


@pytest.mark.asyncio
async def test_router_quiet_noop_renders_no_change(db_session: AsyncSession):
    """中间显示按钮 quiet:noop 不该改任何字段 · 只重渲。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 5004)

    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 5004, "quiet:noop",  # type: ignore[arg-type]
    )
    assert "安静时段" in reply.text  # 重渲了
    cfg = await _read_config(db_session, user.id)
    # 默认值不动
    assert cfg is not None
    assert cfg.quiet_hours_enabled is True
    assert cfg.quiet_hours_start == 23
    assert cfg.quiet_hours_end == 7


@pytest.mark.asyncio
async def test_router_quiet_cross_user_via_chat(db_session: AsyncSession):
    """🔴 router 层的跨用户隔离:chat 5005 绑定 A · 所有 quiet 操作只影响 A 的 config。

    比模块层测试更强 · 走 router 完整路径(含 resolve_user_id chat→user)。
    """
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    # B 的 config 预置非默认值
    db_session.add(NotificationConfig(
        user_id=user_b.id,
        tg_chat_id="b-chat-router",
        quiet_hours_enabled=False,
        quiet_hours_start=10,
        quiet_hours_end=20,
        quiet_hours_tz="UTC",
    ))
    await _bind(db_session, user_a.id, 5005)  # chat 5005 → A

    redis = _FakeRedis()
    ch = _FakeCH()

    # 通过 chat 5005 操作 quiet · 期望只动 A · B 不动
    await router.handle_callback(db_session, redis, ch, 5005, "quiet:toggle")  # type: ignore[arg-type]
    await router.handle_callback(db_session, redis, ch, 5005, "quiet:s+")  # type: ignore[arg-type]
    await router.handle_callback(db_session, redis, ch, 5005, "quiet:e+")  # type: ignore[arg-type]

    cfg_b = await _read_config(db_session, user_b.id)
    assert cfg_b is not None
    assert cfg_b.tg_chat_id == "b-chat-router"
    assert cfg_b.quiet_hours_enabled is False  # 不动
    assert cfg_b.quiet_hours_start == 10       # 不动
    assert cfg_b.quiet_hours_end == 20         # 不动
    assert cfg_b.quiet_hours_tz == "UTC"       # 不动
