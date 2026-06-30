"""铂金 per-user 开关 guard pytest(多账户 PR-3)。

★重点:① user_id=None 仍读写【旧全局 key】(向后兼容·现在跑的智能/托管交易 + admin toggle 靠它·不破)·
② per-user 开关默认 OFF · ③ per-user 与全局完全独立(互不覆盖)· ④ 不同铂金用户 uid 互相独立(不串户)·
⑤ key 格式钉死(intelligent:enabled / intelligent:enabled:{uid},managed 同构)。
★纯逻辑 FakeRedis · 本地秒级真跑 · 不需 redis(同 test_auto_guard 范式)。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.virtual_trading.intelligent import guard as iguard
from app.services.virtual_trading.managed import guard as mguard

_UID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_UID2 = uuid.UUID("22222222-2222-2222-2222-222222222222")


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)

    async def set(self, k: str, v: Any) -> None:
        self.kv[k] = v


# 两个 guard 模块对称,同一套断言覆盖(global_key = 各自旧全局开关 key)。
_GUARDS = [
    pytest.param(iguard, "intelligent:enabled", id="intelligent"),
    pytest.param(mguard, "managed:enabled", id="managed"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("guard", "global_key"), _GUARDS)
async def test_global_none_uses_old_key(guard: Any, global_key: str) -> None:
    """★向后兼容:user_id=None 读写【旧全局 key】· 默认 OFF · 不碰任何 per-user key。"""
    r = _FakeRedis()
    assert await guard.is_enabled(r) is False  # 默认 OFF(key 缺失)
    await guard.set_enabled(r, enabled=True)
    assert await guard.is_enabled(r) is True
    assert r.kv[global_key] == "1"  # ★写的是旧全局 key(无 uid 后缀)
    assert list(r.kv.keys()) == [global_key]  # ★只碰全局 key · 没生成任何 per-user key
    await guard.set_enabled(r, enabled=False)
    assert await guard.is_enabled(r) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("guard", "global_key"), _GUARDS)
async def test_per_user_default_off_and_toggle(guard: Any, global_key: str) -> None:
    """per-user 开关默认 OFF + 开/关 · key 格式 = 全局 key + :uid。"""
    r = _FakeRedis()
    assert await guard.is_enabled(r, _UID) is False  # per-user 默认 OFF
    await guard.set_enabled(r, enabled=True, user_id=_UID)
    assert await guard.is_enabled(r, _UID) is True
    assert r.kv[f"{global_key}:{_UID}"] == "1"  # ★per-user key 格式钉死
    await guard.set_enabled(r, enabled=False, user_id=_UID)
    assert await guard.is_enabled(r, _UID) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("guard", "global_key"), _GUARDS)
async def test_per_user_independent_from_global(guard: Any, global_key: str) -> None:
    """★per-user 与全局完全独立:开 per-user 不带开全局(现在跑的全局账户),反之亦然。"""
    r = _FakeRedis()
    await guard.set_enabled(r, enabled=True, user_id=_UID)
    assert await guard.is_enabled(r, _UID) is True
    assert await guard.is_enabled(r) is False  # ★全局仍 OFF(没被 per-user 带开)
    assert global_key not in r.kv  # 全局 key 根本没被写

    r2 = _FakeRedis()
    await guard.set_enabled(r2, enabled=True)  # 开全局
    assert await guard.is_enabled(r2) is True
    assert await guard.is_enabled(r2, _UID) is False  # ★per-user 仍 OFF(全局不覆盖 per-user)


@pytest.mark.asyncio
@pytest.mark.parametrize(("guard", "global_key"), _GUARDS)
async def test_two_users_independent(guard: Any, global_key: str) -> None:
    """★不同铂金用户互相独立(不串户):开 uid1 不影响 uid2。"""
    r = _FakeRedis()
    await guard.set_enabled(r, enabled=True, user_id=_UID)
    assert await guard.is_enabled(r, _UID) is True
    assert await guard.is_enabled(r, _UID2) is False  # 另一铂金用户独立
    assert f"{global_key}:{_UID}" in r.kv
    assert f"{global_key}:{_UID2}" not in r.kv
