"""铂金 per-user 开仓参数 guard pytest(多账户 PR-7a)。

★重点:① user_id=None 读写【旧全局 key】(向后兼容·现在跑的智能/托管交易 + admin 靠它·不破)·
② 给定 uid set → 只写 per-user key f"{base}:{uid}"(不动全局)· ③ ★决策③:铂金没单独设过某参数 →
get(uid) 回退【全局当前值】(不是硬默认)· ④ per-user 设了则只覆盖该 uid(全局 + 其它 uid 不变)·
⑤ 不同铂金 uid 互相独立(不串户)· ⑥ ★决策 B:只【开仓参数】per-user;平仓参数(智能 close 读
weights·托管 exit/tp_pct)仍全局——close 调 getter 不传 uid = 永远全局·不受铂金 per-user 影响。
★纯逻辑 FakeRedis · 本地秒级真跑 · 不需 redis(同 test_platinum_guard_peruser 范式)。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
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


# 开仓参数(margin/leverage/max)· 两 guard 对称 ·
# (guard, getter, setter, base_key, 全局样本, per-user 样本, DEFAULT)
_OPEN_PARAMS = [
    pytest.param(
        iguard, "get_open_margin", "set_open_margin",
        "intelligent:open:margin", Decimal("250"), Decimal("300"), Decimal("100"),
        id="i-margin",
    ),
    pytest.param(
        iguard, "get_open_leverage", "set_open_leverage",
        "intelligent:open:leverage", 8, 12, 5, id="i-leverage",
    ),
    pytest.param(
        iguard, "get_max_positions", "set_max_positions",
        "intelligent:open:max_positions", 30, 40, 50, id="i-max",
    ),
    pytest.param(
        mguard, "get_open_margin", "set_open_margin",
        "managed:open:margin", Decimal("250"), Decimal("300"), Decimal("100"),
        id="m-margin",
    ),
    pytest.param(
        mguard, "get_open_leverage", "set_open_leverage",
        "managed:open:leverage", 8, 12, 5, id="m-leverage",
    ),
    pytest.param(
        mguard, "get_max_positions", "set_max_positions",
        "managed:open:max_positions", 30, 40, 50, id="m-max",
    ),
]

# 智能策略标量参数(threshold / atr_stop / atr_tp · float)·
_STRAT_SCALARS = [
    pytest.param(
        "get_strategy_threshold", "set_strategy_threshold",
        "intelligent:strategy:threshold", 4.0, 5.0, 3.0, id="threshold",
    ),
    pytest.param(
        "get_strategy_atr_stop_mult", "set_strategy_atr_stop_mult",
        "intelligent:strategy:atr_stop_mult", 2.5, 3.0, 2.0, id="atr_stop",
    ),
    pytest.param(
        "get_strategy_atr_tp_mult", "set_strategy_atr_tp_mult",
        "intelligent:strategy:atr_tp_mult", 5.0, 6.0, 4.0, id="atr_tp",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guard", "getter_name", "setter_name", "base_key", "g_sample", "u_sample", "default"),
    _OPEN_PARAMS,
)
async def test_open_param_peruser(
    guard: Any, getter_name: str, setter_name: str, base_key: str,
    g_sample: Any, u_sample: Any, default: Any,
) -> None:
    """开仓参数 per-user 全契约:向后兼容 + 决策③回退全局 + per-user 覆盖 + uid 隔离。"""
    r = _FakeRedis()
    get = getattr(guard, getter_name)
    set_ = getattr(guard, setter_name)

    # ① 都没设 → DEFAULT(全局 + 任意 uid)
    assert await get(r) == default
    assert await get(r, _UID) == default

    # ② 全局 set(无 uid)→ 只写旧全局 key · 没生成任何 per-user key
    await set_(r, g_sample)
    assert r.kv[base_key] == str(g_sample)
    assert list(r.kv.keys()) == [base_key]

    # ③ ★决策③:uid 没单独设过 → get(uid) 回退【全局当前值】(不是 DEFAULT)
    assert await get(r, _UID) == g_sample

    # ④ per-user set(uid)→ 只写 per-user key f"{base}:{uid}" · 全局一字不动
    await set_(r, u_sample, _UID)
    assert r.kv[f"{base_key}:{_UID}"] == str(u_sample)
    assert r.kv[base_key] == str(g_sample)

    # ⑤ 该 uid 读自己值 · 全局读全局 · 另一 uid 回退全局(不串户)
    assert await get(r, _UID) == u_sample
    assert await get(r) == g_sample
    assert await get(r, _UID2) == g_sample


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("getter_name", "setter_name", "base_key", "g_sample", "u_sample", "default"),
    _STRAT_SCALARS,
)
async def test_strategy_scalar_peruser(
    getter_name: str, setter_name: str, base_key: str,
    g_sample: float, u_sample: float, default: float,
) -> None:
    """智能策略标量参数(阈值/ATR 倍数)per-user 全契约(同开仓参数)。"""
    r = _FakeRedis()
    get = getattr(iguard, getter_name)
    set_ = getattr(iguard, setter_name)

    assert await get(r) == default
    assert await get(r, _UID) == default

    await set_(r, g_sample)
    assert r.kv[base_key] == str(g_sample)
    assert list(r.kv.keys()) == [base_key]

    assert await get(r, _UID) == g_sample  # 决策③回退全局

    await set_(r, u_sample, _UID)
    assert r.kv[f"{base_key}:{_UID}"] == str(u_sample)
    assert r.kv[base_key] == str(g_sample)

    assert await get(r, _UID) == u_sample
    assert await get(r) == g_sample
    assert await get(r, _UID2) == g_sample


@pytest.mark.asyncio
async def test_strategy_weights_peruser() -> None:
    """6 权重 per-user:★key 后缀必须拼在完整 base 末尾(weight_boll:{uid})· 回退全局 · 隔离。"""
    r = _FakeRedis()
    boll_key = "intelligent:strategy:weight_boll"

    # 默认(全局 + uid 都没设)→ 默认权重
    assert (await iguard.get_strategy_weights(r))["boll"] == 2.0
    assert (await iguard.get_strategy_weights(r, _UID))["boll"] == 2.0

    # 全局 set boll → 只写全局 weight key
    await iguard.set_strategy_weight(r, "boll", 3.0)
    assert r.kv[boll_key] == "3.0"

    # ★决策③:uid 没设 boll → 回退全局 3.0
    assert (await iguard.get_strategy_weights(r, _UID))["boll"] == 3.0

    # per-user set boll → key = 完整 base + :uid(后缀在末尾)· 全局不动
    await iguard.set_strategy_weight(r, "boll", 5.0, _UID)
    assert r.kv[f"{boll_key}:{_UID}"] == "5.0"
    assert r.kv[boll_key] == "3.0"

    # 该 uid boll 读自己 5.0;全局/另一 uid 读全局 3.0(不串户)
    assert (await iguard.get_strategy_weights(r, _UID))["boll"] == 5.0
    assert (await iguard.get_strategy_weights(r))["boll"] == 3.0
    assert (await iguard.get_strategy_weights(r, _UID2))["boll"] == 3.0

    # 该 uid 其它指标没设 → 回退全局默认(macd=1.5)
    assert (await iguard.get_strategy_weights(r, _UID))["macd"] == 1.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guard", "getter", "setter", "base_key"),
    [
        pytest.param(
            iguard, "get_allow_long", "set_allow_long",
            "intelligent:open:allow_long", id="i-long",
        ),
        pytest.param(
            iguard, "get_allow_short", "set_allow_short",
            "intelligent:open:allow_short", id="i-short",
        ),
        pytest.param(
            mguard, "get_allow_long", "set_allow_long",
            "managed:open:allow_long", id="m-long",
        ),
    ],
)
async def test_direction_switch_peruser(
    guard: Any, getter: str, setter: str, base_key: str,
) -> None:
    """★PR-8 方向开关 per-user 全契约:★默认 ON(!= "0")· 决策③回退全局 · uid 隔离。"""
    r = _FakeRedis()
    get = getattr(guard, getter)
    set_ = getattr(guard, setter)

    # ① ★默认 ON(从未设过 = 现状·绝不能默认 OFF)
    assert await get(r) is True
    assert await get(r, _UID) is True

    # ② 全局 set OFF → 只写全局 key
    await set_(r, on=False)
    assert r.kv[base_key] == "0"
    assert list(r.kv.keys()) == [base_key]
    assert await get(r) is False

    # ③ ★决策③:uid 没单独设 → 回退全局当前值(现 OFF)
    assert await get(r, _UID) is False

    # ④ per-user set ON(uid)→ 只写 per-user key · 全局仍 OFF
    await set_(r, on=True, user_id=_UID)
    assert r.kv[f"{base_key}:{_UID}"] == "1"
    assert r.kv[base_key] == "0"

    # ⑤ 该 uid 自己 ON · 全局仍 OFF · 另一 uid 回退全局 OFF(不串户)
    assert await get(r, _UID) is True
    assert await get(r) is False
    assert await get(r, _UID2) is False


@pytest.mark.asyncio
async def test_close_reads_global_not_peruser_decision_b() -> None:
    """★决策 B:close 调 getter 不传 uid → 永远读全局·不受铂金 per-user 设置影响(close.py 零改的依据)。

    intelligent close.py:122 get_strategy_weights(redis)、managed close.py:112-113
    get_exit_switches/get_tp_pct 都不传 uid → user_id=None → 全局 key,平仓参数全局。
    """
    r = _FakeRedis()
    # 铂金设了自己的 per-user 权重(影响开仓算分)
    await iguard.set_strategy_weight(r, "boll", 9.0, _UID)
    # close 那行(无 uid)读到的仍是全局默认 2.0 · 铂金 per-user 不漏进平仓信号反转
    assert (await iguard.get_strategy_weights(r))["boll"] == 2.0

    # 托管退出参数本就无 user_id 形参(全局-only)· 调用即全局
    assert await mguard.get_exit_switches(r) == {"tp": True, "signal": True, "timeout": True}
    assert await mguard.get_tp_pct(r) == mguard.DEFAULT_TP_PCT
