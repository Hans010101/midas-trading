"""铂金自助端点越权防护 pytest(多账户 PR-5a)· 🔴安全红线:A 的 token 拿不到/改不了 B 的数据。

★重点:① 非铂金→403(文案"需铂金权限")· 未登录→401 · ② per-user 开关隔离(A toggle 不影响 B)·
③ 看板隔离(A 看不到 B 影子仓)· ④ OpenAPI /platinum 路径/参数无 user_id(签名层结构性杜绝越权)。
需 DB + Redis · CI 真跑(④ OpenAPI 纯静态本地可跑)。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clickhouse
from app.api.v1 import platinum_self
from app.main import app
from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.services.auth import issue_session
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.managed import account as macc
from tests.factories import make_user


async def _no_marks(_client: Any, _symbols: list[str]) -> dict[str, Any]:
    """假 marks(无活 CH)· 返空 → 浮盈 None · 持仓仍出现(隔离测试只关心哪些仓出现)。"""
    return {}


@pytest.fixture(autouse=True)
def _ch_override():  # noqa: ANN202
    # status/positions 走 ClickHouseDep · 测试无 lifespan → 假 holder(无活仓时不触发 fetch)。
    app.dependency_overrides[get_clickhouse] = lambda: SimpleNamespace(_client=object())
    yield
    app.dependency_overrides.pop(get_clickhouse, None)


async def _platinum_headers(db: AsyncSession, **overrides: Any) -> tuple[Any, dict[str, str]]:
    user = await make_user(db, is_platinum=True, **overrides)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


# ── ① 鉴权门:非铂金 403 · 未登录 401 ──────────────────────────────────
@pytest.mark.asyncio
async def test_non_platinum_403(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, role="user")  # 登录但非铂金
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/platinum/intelligent/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "需铂金权限"  # ★明确文案(Hans 定)


@pytest.mark.asyncio
async def test_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/platinum/intelligent/status")
    assert r.status_code == 401


# ── ② per-user 开关隔离:A toggle 不影响 B ─────────────────────────────
@pytest.mark.asyncio
async def test_toggle_isolated_per_user(client: AsyncClient, db_session: AsyncSession) -> None:
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    # A 开自己的智能开关
    r = await client.post(
        "/api/v1/platinum/intelligent/toggle", json={"enabled": True}, headers=ha)
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["account_ready"] is True  # ★开则幂等建自己的影子账户
    # ★B 的开关不受影响(per-user key={uid} 隔离)
    rb = await client.get("/api/v1/platinum/intelligent/status", headers=hb)
    assert rb.status_code == 200
    assert rb.json()["enabled"] is False
    # A 自己再查仍 True
    ra = await client.get("/api/v1/platinum/intelligent/status", headers=ha)
    assert ra.json()["enabled"] is True


@pytest.mark.asyncio
async def test_managed_toggle_isolated_per_user(client: AsyncClient, db_session: AsyncSession) -> None:
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    r = await client.post(
        "/api/v1/platinum/managed/toggle", json={"enabled": True}, headers=ha)
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    rb = await client.get("/api/v1/platinum/managed/status", headers=hb)
    assert rb.json()["enabled"] is False  # ★B 不受影响


# ── ③ 看板隔离:A 看不到 B 的影子仓 ───────────────────────────────────
@pytest.mark.asyncio
async def test_positions_isolated_cannot_see_others(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr(platinum_self, "select_premium_index_marks", _no_marks)  # 无活 CH
    _a, ha = await _platinum_headers(db_session)
    b_user, _hb = await _platinum_headers(db_session)
    # 在 B 的影子账户建一仓
    b_acc = await iacc.ensure_intelligent_account_for_user(db_session, b_user.id)
    db_session.add(VirtualPerpPosition(
        account_id=b_acc.id, symbol="BTCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        intelligent=True,
    ))
    await db_session.commit()
    # ★A 的 token 查活仓 → 看不到 B 的仓(account_id 收窄到 A 自己的影子账户)
    r = await client.get("/api/v1/platinum/intelligent/positions", headers=ha)
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0
    # B 自己查得到(双确认隔离方向正确)
    b_token = (await _bearer(db_session, b_user))["Authorization"]
    rb = await client.get(
        "/api/v1/platinum/intelligent/positions",
        headers={"Authorization": b_token},
    )
    assert rb.json()["total"] == 1


async def _bearer(db: AsyncSession, user: Any) -> dict[str, str]:
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


# ── ④ OpenAPI 签名层杜绝越权:/platinum 路径/参数无 user_id(纯静态·本地可跑)──
def test_openapi_platinum_paths_have_no_user_id() -> None:
    schema = app.openapi()
    plat_paths = {p: item for p, item in schema["paths"].items() if "/platinum/" in p}
    assert plat_paths, "应有 /platinum 自助路径"
    for path, item in plat_paths.items():
        assert "{user_id}" not in path  # ★path 无 user_id
        for method in item.values():
            if not isinstance(method, dict):
                continue
            for param in method.get("parameters", []):
                assert param.get("name") != "user_id"  # ★query/path 参数无 user_id
    # toggle body 只有 enabled(IntelligentToggleIn/ManagedToggleIn)· 无 user_id → 结构上 A 指定不了 B


# ── ⑤ 参数自助 per-user 隔离 + 校验(PR-7b · 决策 B 只开仓参数)──────────────
@pytest.mark.asyncio
async def test_open_margin_isolated_per_user(client: AsyncClient, db_session: AsyncSession) -> None:
    """A/B 各设各的每单本金 · 互不串(per-user key={uid}·设参数不建账户)。"""
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    ra = await client.post(
        "/api/v1/platinum/intelligent/open-margin", json={"margin": 250}, headers=ha)
    rb = await client.post(
        "/api/v1/platinum/intelligent/open-margin", json={"margin": 300}, headers=hb)
    assert ra.status_code == 200
    assert ra.json()["open_margin"] == 250.0
    assert ra.json()["account_ready"] is False  # ★设参数不建账户
    assert rb.json()["open_margin"] == 300.0
    # ★交叉:A 再查仍 250(B 设 300 不影响 A)
    sa = await client.get("/api/v1/platinum/intelligent/status", headers=ha)
    assert sa.json()["open_margin"] == 250.0


@pytest.mark.asyncio
async def test_managed_open_leverage_isolated_per_user(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    ra = await client.post(
        "/api/v1/platinum/managed/open-leverage", json={"leverage": 12}, headers=ha)
    rb = await client.post(
        "/api/v1/platinum/managed/open-leverage", json={"leverage": 3}, headers=hb)
    assert ra.json()["open_leverage"] == 12
    assert rb.json()["open_leverage"] == 3


@pytest.mark.asyncio
async def test_strategy_params_isolated_per_user(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """智能策略参数 per-user:A 设自己的阈值/权重 · B 读到的是 B 自己的(不串)。"""
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    pa = {"threshold": 5.0, "atr_stop_mult": 2.5, "atr_tp_mult": 5.0,
          "weights": {"boll": 3, "macd": 1, "ma": 1, "rsi": 1, "kdj": 1, "extreme": 1}}
    pb = {"threshold": 6.0, "atr_stop_mult": 3.0, "atr_tp_mult": 6.0,
          "weights": {"boll": 4, "macd": 2, "ma": 2, "rsi": 2, "kdj": 2, "extreme": 2}}
    ra = await client.post("/api/v1/platinum/intelligent/strategy-params", json=pa, headers=ha)
    rb = await client.post("/api/v1/platinum/intelligent/strategy-params", json=pb, headers=hb)
    assert ra.status_code == 200
    assert ra.json()["threshold"] == 5.0
    assert ra.json()["weights"]["boll"] == 3.0
    assert rb.json()["threshold"] == 6.0
    # ★A 读回自己的 5.0(B 设 6.0 不影响)
    sa = await client.get("/api/v1/platinum/intelligent/strategy-params", headers=ha)
    assert sa.json()["threshold"] == 5.0
    assert sa.json()["weights"]["boll"] == 3.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/platinum/intelligent/open-margin", {"margin": 5}),        # < 10
        ("/api/v1/platinum/intelligent/open-margin", {"margin": 99999}),    # > 10000
        ("/api/v1/platinum/intelligent/open-leverage", {"leverage": 0}),    # < 1
        ("/api/v1/platinum/intelligent/open-leverage", {"leverage": 99}),   # > 20
        ("/api/v1/platinum/intelligent/max-positions", {"max_positions": 0}),
        ("/api/v1/platinum/managed/open-margin", {"margin": 5}),
        ("/api/v1/platinum/managed/max-positions", {"max_positions": -1}),
    ],
)
async def test_param_validation_400(
    client: AsyncClient, db_session: AsyncSession, path: str, body: dict[str, Any],
) -> None:
    _a, ha = await _platinum_headers(db_session)
    r = await client.post(path, json=body, headers=ha)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_strategy_params_bad_weights_400(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _a, ha = await _platinum_headers(db_session)
    # 缺指标
    bad = {"threshold": 3, "atr_stop_mult": 2, "atr_tp_mult": 4, "weights": {"boll": 1}}
    r = await client.post("/api/v1/platinum/intelligent/strategy-params", json=bad, headers=ha)
    assert r.status_code == 400
    # 负权重
    neg = {"threshold": 3, "atr_stop_mult": 2, "atr_tp_mult": 4,
           "weights": {"boll": -1, "macd": 1, "ma": 1, "rsi": 1, "kdj": 1, "extreme": 1}}
    r2 = await client.post("/api/v1/platinum/intelligent/strategy-params", json=neg, headers=ha)
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_param_set_non_platinum_403(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """★参数 set 端点同样挂 PlatinumDep:非铂金调 → 403(不只 GET 被拦)。"""
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.post(
        "/api/v1/platinum/intelligent/open-margin", json={"margin": 250},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ── ⑥ 账户操作自助:reset/capital + ★平仓越权(PR-7c)────────────────────
@pytest.mark.asyncio
async def test_capital_updates_own_account(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """改起始资金:ensure 先建 → account_ready + initial_capital 更新(只我自己)。"""
    _a, ha = await _platinum_headers(db_session)
    r = await client.post(
        "/api/v1/platinum/intelligent/account/capital", json={"amount": 5000}, headers=ha)
    assert r.status_code == 200
    assert r.json()["account_ready"] is True   # ensure 先建
    assert r.json()["initial_capital"] == 5000.0


@pytest.mark.asyncio
async def test_capital_rejects_non_positive(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _a, ha = await _platinum_headers(db_session)
    r = await client.post(
        "/api/v1/platinum/managed/account/capital", json={"amount": 0}, headers=ha)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_reset_clears_own_positions(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr(platinum_self, "select_premium_index_marks", _no_marks)
    a_user, ha = await _platinum_headers(db_session)
    acc = await macc.ensure_managed_account_for_user(db_session, a_user.id)
    db_session.add(VirtualPerpPosition(
        account_id=acc.id, symbol="BTCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        managed=True,
    ))
    await db_session.commit()
    r = await client.post("/api/v1/platinum/managed/account/reset", headers=ha)
    assert r.status_code == 200
    assert r.json()["open_positions"] == 0  # ★清零后无活仓


@pytest.mark.asyncio
async def test_close_one_rejects_others_position(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """★越权红线:A 用自己 token 平 B 的 position_id → 404(owner==caller·不泄露他人仓存在)。"""
    a_user, ha = await _platinum_headers(db_session)
    b_user, _hb = await _platinum_headers(db_session)
    await macc.ensure_managed_account_for_user(db_session, a_user.id)  # A 有自己影子账户
    b_acc = await macc.ensure_managed_account_for_user(db_session, b_user.id)
    pos = VirtualPerpPosition(
        account_id=b_acc.id, symbol="BTCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        managed=True,
    )
    db_session.add(pos)
    await db_session.commit()
    # ★A 平 B 的仓 → 404(端点层 pos.account_id != A 影子账户)
    r = await client.post(f"/api/v1/platinum/managed/positions/{pos.id}/close", headers=ha)
    assert r.status_code == 404
    # B 的仓没被平(越权拦在调引擎前)
    await db_session.refresh(pos)
    assert pos.closed_at is None


@pytest.mark.asyncio
async def test_close_one_nonexistent_404(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    a_user, ha = await _platinum_headers(db_session)
    await macc.ensure_managed_account_for_user(db_session, a_user.id)
    r = await client.post("/api/v1/platinum/managed/positions/999999/close", headers=ha)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_close_all_empty_when_no_account(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """没开过托管(无影子账户)→ close-all 安静返 0(不报错·不碰全局)。"""
    _a, ha = await _platinum_headers(db_session)
    r = await client.post("/api/v1/platinum/managed/positions/close-all", headers=ha)
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "closed": 0, "total": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/platinum/intelligent/account/reset",
        "/api/v1/platinum/managed/account/capital",
        "/api/v1/platinum/managed/positions/close-all",
    ],
)
async def test_account_ops_non_platinum_403(
    client: AsyncClient, db_session: AsyncSession, path: str,
) -> None:
    """★账户操作/平仓端点同样挂 PlatinumDep:非铂金 → 403。"""
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    body = {"amount": 100} if "capital" in path else None
    r = await client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# ── ⑦ 方向过滤器 per-user 隔离 + 校验(PR-8)──────────────────────────────
@pytest.mark.asyncio
async def test_intelligent_allow_direction_isolated_per_user(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """A 关自己的做空 → 只 A 的 allow_short False · B 默认仍多空都 ON(不串)。"""
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    ra = await client.post(
        "/api/v1/platinum/intelligent/allow-direction",
        json={"which": "short", "on": False}, headers=ha)
    assert ra.status_code == 200
    assert ra.json()["allow_short"] is False
    assert ra.json()["allow_long"] is True   # ★做多不受影响
    rb = await client.get("/api/v1/platinum/intelligent/status", headers=hb)
    assert rb.json()["allow_short"] is True   # ★B 默认 ON(不串)
    assert rb.json()["allow_long"] is True


@pytest.mark.asyncio
async def test_managed_allow_long_isolated_per_user(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    ra = await client.post(
        "/api/v1/platinum/managed/allow-long", json={"on": False}, headers=ha)
    assert ra.status_code == 200
    assert ra.json()["allow_long"] is False
    rb = await client.get("/api/v1/platinum/managed/status", headers=hb)
    assert rb.json()["allow_long"] is True   # ★B 默认 ON


@pytest.mark.asyncio
async def test_allow_direction_bad_which_400(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _a, ha = await _platinum_headers(db_session)
    r = await client.post(
        "/api/v1/platinum/intelligent/allow-direction",
        json={"which": "sideways", "on": True}, headers=ha)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_allow_direction_non_platinum_403(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.post(
        "/api/v1/platinum/intelligent/allow-direction",
        json={"which": "long", "on": False},
        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
