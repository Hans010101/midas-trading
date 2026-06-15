"""bot 入站编排 pytest · 0025 M1-G G3 + G4(下单)。

重点:① 未绑定 → 引导绑定;② 命令 / 回调路由正确;③ 🔴 安全边界 —— user_id 只从
chat 绑定取(查询/下单永远只作用于该 chat 绑定账号,跨用户隔离);④ 下单必经二次确认
(选方向不成交,确认才成交);⑤ DP11 限流。
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.models.virtual import PositionSide, VirtualPosition
from app.services.bot import router
from app.services.bot.renderers.telegram import render_for_telegram
from app.services.bot.replies import InboundMessage, ReplyModel
from tests.factories import make_user, make_virtual_account


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
    def __init__(
        self,
        klines: list[Any] | None = None,
        exists: set[tuple[str, str]] | None = None,
    ) -> None:
        self._klines = klines or []
        # 扫库存在性:命中的 (market, canonical_symbol) 集合(detect_symbol_markets 用)
        self._exists = exists or set()
        self._client = object()

    async def select_kline(self, **_kwargs: Any) -> list[Any]:
        return list(self._klines)

    async def symbol_exists(
        self, market: str, symbol: str, instrument: str = "spot",  # noqa: ARG002
    ) -> bool:
        return (market, symbol) in self._exists


def _bar(close: float) -> SimpleNamespace:
    return SimpleNamespace(close=Decimal(str(close)), volume=Decimal("1"))


async def _bind(db: AsyncSession, user_id: Any, chat_id: int) -> None:
    db.add(NotificationConfig(user_id=user_id, tg_chat_id=str(chat_id)))
    await db.commit()


@pytest.mark.asyncio
async def test_command_unbound_prompts_binding(db_session: AsyncSession):
    """没绑定的 chat → 不泄露任何数据,引导去网页端绑定。"""
    reply = await router.handle_command(
        db_session, _FakeRedis(), _FakeCH(), 999, "/menu",  # type: ignore[arg-type]
    )
    assert "绑定" in reply.text
    assert reply.keyboard is None


@pytest.mark.asyncio
async def test_command_menu_when_bound(db_session: AsyncSession):
    user = await make_user(db_session)
    await _bind(db_session, user.id, 12345)
    reply = await router.handle_command(
        db_session, _FakeRedis(), _FakeCH(), 12345, "/menu",  # type: ignore[arg-type]
    )
    assert reply.keyboard is not None
    assert "inline_keyboard" in reply.keyboard


@pytest.mark.asyncio
async def test_callback_positions_bound(db_session: AsyncSession):
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    db_session.add(
        VirtualPosition(
            account_id=acct.id, symbol="NVDA", market="us",
            position_side=PositionSide.LONG,
            quantity=Decimal("5"), avg_entry_price=Decimal("100"),
        ),
    )
    await _bind(db_session, user.id, 222)

    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 222, "act:positions",  # type: ignore[arg-type]
    )
    assert "NVDA" in reply.text
    assert "VIRTUAL" not in reply.text  # 产品决策:不再带 VIRTUAL 徽章


@pytest.mark.asyncio
async def test_ask_quote_session_then_symbol(db_session: AsyncSession):
    user = await make_user(db_session)
    await _bind(db_session, user.id, 333)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0), _bar(120.0)])

    # 点「行情→美股」→ 写会话态 + 提示输代码
    ask = await router.handle_callback(
        db_session, redis, ch, 333, "ask:quote:us",  # type: ignore[arg-type]
    )
    assert "代码" in ask.text
    assert json.loads(redis._d["tg_session:333"]) == {"awaiting": "quote", "market": "us"}

    # 续输代码 → 行情卡
    quote = await router.handle_command(
        db_session, redis, ch, 333, "NVDA",  # type: ignore[arg-type]
    )
    assert "NVDA" in quote.text
    assert "tg_session:333" not in redis._d  # 会话已清


@pytest.mark.asyncio
async def test_user_isolation_positions(db_session: AsyncSession):
    """🔴 安全:chat 绑定 A,A 无持仓;B 有持仓 → 该 chat 查持仓返回空(绝不串到 B)。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    acct_b = await make_virtual_account(db_session, user_id=user_b.id, market="us")
    db_session.add(
        VirtualPosition(
            account_id=acct_b.id, symbol="TSLA", market="us",
            position_side=PositionSide.LONG,
            quantity=Decimal("3"), avg_entry_price=Decimal("200"),
        ),
    )
    await _bind(db_session, user_a.id, 444)  # chat 444 绑定 A

    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 444, "act:positions",  # type: ignore[arg-type]
    )
    assert "TSLA" not in reply.text  # B 的持仓绝不出现
    assert "没有活仓" in reply.text


@pytest.mark.asyncio
async def test_unknown_callback_falls_back_to_menu(db_session: AsyncSession):
    user = await make_user(db_session)
    await _bind(db_session, user.id, 555)
    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 555, "bogus:xyz",  # type: ignore[arg-type]
    )
    assert reply.keyboard is not None
    assert "inline_keyboard" in reply.keyboard


# ── 下单流程(G4)· 必经二次确认 + 跨用户隔离 + 限流 ─────────────────────


async def _positions(db: AsyncSession, account_id: int) -> list[VirtualPosition]:
    rows = await db.scalars(
        select(VirtualPosition).where(VirtualPosition.account_id == account_id),
    )
    return list(rows)


@pytest.mark.asyncio
async def test_order_requires_confirm_then_fills(db_session: AsyncSession):
    """选方向只出预览【不成交】;点确认才真正下单(DP8 必经二次确认)。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, 700)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0)])

    # 下单 → 选市场
    await router.handle_callback(db_session, redis, ch, 700, "menu:order")  # type: ignore[arg-type]
    await router.handle_callback(db_session, redis, ch, 700, "omkt:us")  # type: ignore[arg-type]
    # 输代码 → 方向页
    dirs = await router.handle_command(db_session, redis, ch, 700, "NVDA")  # type: ignore[arg-type]
    assert "选择操作" in dirs.text
    # 选「买入」→ 预览(确认页)· 此刻【还没下单】
    preview = await router.handle_callback(db_session, redis, ch, 700, "odir:buy")  # type: ignore[arg-type]
    assert "确认" in preview.text
    assert not await _positions(db_session, acct.id), "选方向后绝不能已成交"
    # 点「确认下单」→ 真正成交
    result = await router.handle_callback(db_session, redis, ch, 700, "ordok")  # type: ignore[arg-type]
    assert "成交" in result.text
    assert "VIRTUAL" not in result.text  # 产品决策:不再带 VIRTUAL 徽章
    assert len(await _positions(db_session, acct.id)) == 1


@pytest.mark.asyncio
async def test_order_cancel_no_execution(db_session: AsyncSession):
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, 701)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0)])

    await router.handle_callback(db_session, redis, ch, 701, "omkt:us")  # type: ignore[arg-type]
    await router.handle_command(db_session, redis, ch, 701, "NVDA")  # type: ignore[arg-type]
    await router.handle_callback(db_session, redis, ch, 701, "odir:buy")  # type: ignore[arg-type]
    cancelled = await router.handle_callback(db_session, redis, ch, 701, "ordno")  # type: ignore[arg-type]
    assert "取消" in cancelled.text
    assert not await _positions(db_session, acct.id)


@pytest.mark.asyncio
async def test_order_cross_user_isolation(db_session: AsyncSession):
    """🔴 chat 绑定 A · 全程确认下单 → 单子只进 A 账户,B 账户绝不被动。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    acct_a = await make_virtual_account(db_session, user_id=user_a.id, market="us")
    acct_b = await make_virtual_account(db_session, user_id=user_b.id, market="us")
    await _bind(db_session, user_a.id, 702)  # chat 702 → A
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0)])

    await router.handle_callback(db_session, redis, ch, 702, "omkt:us")  # type: ignore[arg-type]
    await router.handle_command(db_session, redis, ch, 702, "NVDA")  # type: ignore[arg-type]
    await router.handle_callback(db_session, redis, ch, 702, "odir:buy")  # type: ignore[arg-type]
    await router.handle_callback(db_session, redis, ch, 702, "ordok")  # type: ignore[arg-type]

    assert len(await _positions(db_session, acct_a.id)) == 1  # A 有单
    assert len(await _positions(db_session, acct_b.id)) == 0  # B 一张没有


@pytest.mark.asyncio
async def test_command_rate_limited(db_session: AsyncSession):
    """超过每分钟命令配额 → 限流提示。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 703)
    redis = _FakeRedis()
    ch = _FakeCH()
    last = None
    for _ in range(router.ratelimit.CMD_LIMIT_PER_MIN + 1):
        last = await router.handle_command(db_session, redis, ch, 703, "/menu")  # type: ignore[arg-type]
    assert last is not None
    assert "频繁" in last.text


# ── 告警规则(G5)· 一键推荐 + 启停 + 🔴 跨用户隔离 ────────────────────────


@pytest.mark.asyncio
async def test_bot_apply_then_toggle_own_rule(db_session: AsyncSession):
    from sqlalchemy import select as _select

    from app.models.alert_rule import AlertRule

    user = await make_user(db_session)
    await _bind(db_session, user.id, 800)
    redis = _FakeRedis()
    ch = _FakeCH()

    # 一键应用推荐 → 建规则
    applied = await router.handle_callback(db_session, redis, ch, 800, "rules:apply")  # type: ignore[arg-type]
    assert "新增" in applied.text
    rule = await db_session.scalar(
        _select(AlertRule).where(AlertRule.user_id == user.id),
    )
    assert rule is not None
    before = rule.enabled

    # 启停自己的规则 → 翻转
    await router.handle_callback(
        db_session, redis, ch, 800, f"rules:toggle:{rule.id}",  # type: ignore[arg-type]
    )
    await db_session.refresh(rule)
    assert rule.enabled is not before


@pytest.mark.asyncio
async def test_bot_rule_toggle_cross_user_blocked(db_session: AsyncSession):
    """🔴 chat 绑 A,试图启停 B 的规则 → B 的规则纹丝不动。"""
    from app.models.alert_rule import AlertRule

    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await _bind(db_session, user_a.id, 801)  # chat 801 → A
    b_rule = AlertRule(
        user_id=user_b.id, market="crypto", symbol=None,
        indicator="fear_greed", operator="lt", threshold=Decimal("20"), enabled=True,
    )
    db_session.add(b_rule)
    await db_session.commit()
    before = b_rule.enabled

    await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 801, f"rules:toggle:{b_rule.id}",  # type: ignore[arg-type]
    )
    await db_session.refresh(b_rule)
    assert b_rule.enabled == before  # B 的规则没被 A 改


# ── 🔴 ADR 0032 阶段一:二次确认必经 红线 + 通道中立核心 ────────────────────


@pytest.mark.asyncio
async def test_ordok_without_confirm_session_does_not_execute(db_session: AsyncSession):
    """🔴 无 order_confirm 会话直接点 ordok → 绝不成交(撮合只由确认态触发)。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, 710)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0)])
    reply = await router.handle_callback(db_session, redis, ch, 710, "ordok")  # type: ignore[arg-type]
    assert not await _positions(db_session, acct.id), "无确认态点 ordok 绝不能成交"
    assert "成交" not in reply.text  # 兜底回主菜单 · 不报成交


@pytest.mark.asyncio
async def test_ordok_skipping_symbol_and_direction_does_not_execute(
    db_session: AsyncSession,
):
    """🔴 刚选完市场(step=order_symbol)就跳点 ordok(跳过标的/方向/预览)→ 不成交。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, 711)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0)])
    await router.handle_callback(db_session, redis, ch, 711, "menu:order")  # type: ignore[arg-type]
    await router.handle_callback(db_session, redis, ch, 711, "omkt:us")  # type: ignore[arg-type]
    # 跳过输代码 / 选方向 / 预览,直接确认
    reply = await router.handle_callback(db_session, redis, ch, 711, "ordok")  # type: ignore[arg-type]
    assert not await _positions(db_session, acct.id), "未到确认态点 ordok 绝不能成交"
    assert "成交" not in reply.text


@pytest.mark.asyncio
async def test_ordok_at_direction_step_does_not_execute(db_session: AsyncSession):
    """🔴 选完标的(step=order_direction · 还没选方向/没预览)就跳点 ordok → 不成交。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, 712)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0)])
    await router.handle_callback(db_session, redis, ch, 712, "menu:order")  # type: ignore[arg-type]
    await router.handle_callback(db_session, redis, ch, 712, "omkt:us")  # type: ignore[arg-type]
    await router.handle_command(db_session, redis, ch, 712, "NVDA")  # type: ignore[arg-type]
    # step 已是 order_direction(预览/确认态尚未建立),跳过 odir 直接 ordok
    reply = await router.handle_callback(db_session, redis, ch, 712, "ordok")  # type: ignore[arg-type]
    assert not await _positions(db_session, acct.id), "方向态点 ordok 绝不能成交"
    assert "成交" not in reply.text


@pytest.mark.asyncio
async def test_handle_inbound_neutral_returns_replymodel(db_session: AsyncSession):
    """通道中立核心:InboundMessage→ReplyModel(未渲染)· 证 router 已脱离 TG 出参;
    渲染后才是 TG 成稿。飞书 P3 将复用同一 handle_inbound + 自己的 renderer。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 713)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0)])
    msg = InboundMessage(
        channel="telegram", channel_uid="713", kind="text", text="/menu",
    )
    reply = await router.handle_inbound(db_session, redis, ch, msg)
    assert isinstance(reply, ReplyModel)
    assert reply.title == "迷你终端"
    assert reply.buttons  # 主菜单按钮(通道中立)非空
    bot = render_for_telegram(reply)  # 渲染成 TG 成稿
    assert "迷你终端" in bot.text
    assert bot.keyboard is not None


# ── P0 交互优化:疑似代码判定 / 市场猜测 / 卡片就地操作 ────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 疑似代码(单 token · 仅字母/数字/斜杠 · 不以 / 开头)
        ("btc", True),
        ("BTC", True),
        ("BTC/USDT", True),
        ("600519", True),
        ("00700", True),
        ("NVDA", True),
        ("eth/usdt", True),
        # 非代码:空 / 命令 / 含空格 / 句子 / 超长 / 中文
        ("", False),
        ("   ", False),
        ("/menu", False),
        ("/price", False),
        ("hello world", False),
        ("how are you", False),
        ("买入 茅台", False),
        ("茅台", False),  # 中文不在允许字符集
        ("A" * 16, False),  # 超过 15 字符上限
    ],
)
def test_looks_like_symbol(text: str, expected: bool):  # noqa: FBT001
    """无会话自由文本疑似代码判定(P0-1)· 纯函数逐用例。"""
    assert router._looks_like_symbol(text) is expected


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("BTC/USDT", "crypto"),  # 含斜杠 → 加密
        ("btc/usdt", "crypto"),  # 大小写无关
        ("600519", "cn"),        # 6 位纯数字 → A股
        ("00700", "hk"),         # 5 位纯数字 → 港股(P0-1 新增分支)
        ("09988", "hk"),
        ("NVDA", "us"),          # 其余 → 美股
        ("AAPL", "us"),
        ("1234", "us"),          # 4 位数字非 cn/hk → 落 us(不误判)
        ("1234567", "us"),       # 7 位数字 → us
    ],
)
def test_guess_market(symbol: str, expected: str):
    """市场猜测(P0-1 · 含新 hk 5 位分支)· 纯函数逐用例。"""
    assert router._guess_market(symbol) == expected


@pytest.mark.asyncio
async def test_free_text_symbol_quotes_without_session(db_session: AsyncSession):
    """🆕 P0-1:无会话直接打代码 → 秒出行情卡(不再被推回菜单/提示)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 720)
    redis = _FakeRedis()
    # 扫库:NVDA 命中美股(不命中加密)→ 单条美股卡
    ch = _FakeCH([_bar(100.0), _bar(120.0)], exists={("us", "NVDA")})
    reply = await router.handle_command(db_session, redis, ch, 720, "NVDA")  # type: ignore[arg-type]
    assert "NVDA" in reply.text
    # 行情卡挂【就地操作】按钮(K线/下单/刷新 · qk/qo/qr),不是 build_hint
    flat = json.dumps(reply.keyboard, ensure_ascii=False)
    assert "qk:us:NVDA" in flat
    assert "qo:us:NVDA" in flat
    assert "qr:us:NVDA" in flat


@pytest.mark.asyncio
async def test_free_text_sentence_falls_to_hint(db_session: AsyncSession):
    """无会话的【句子】(多 token)→ 仍落提示,不当代码查。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 721)
    reply = await router.handle_command(
        db_session, _FakeRedis(), _FakeCH([_bar(100.0)]), 721, "how are you",  # type: ignore[arg-type]
    )
    assert "/menu" in reply.text or "功能菜单" in reply.text


@pytest.mark.asyncio
async def test_card_qr_refresh_requotes(db_session: AsyncSession):
    """🆕 P0-2:点行情卡「🔄 刷新」(qr)→ 重新出行情(精确复现原查询)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 722)
    ch = _FakeCH([_bar(100.0), _bar(120.0)])
    reply = await router.handle_callback(db_session, _FakeRedis(), ch, 722, "qr:us:NVDA")  # type: ignore[arg-type]
    assert "NVDA" in reply.text


@pytest.mark.asyncio
async def test_card_qo_jumps_to_direction_reusing_confirm_chain(db_session: AsyncSession):
    """🆕 P0-2:点行情卡「🛒 下单」(qo)→ 直达方向页 + 写 order_direction 会话(复用现有
    二次确认链路 · 此刻【不成交】)。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, 723)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0)])
    reply = await router.handle_callback(db_session, redis, ch, 723, "qo:us:NVDA")  # type: ignore[arg-type]
    assert "选择操作" in reply.text
    # 会话进入方向选择态(只存「下什么」· 不存身份)
    assert json.loads(redis._d["tg_session:723"]) == {
        "step": "order_direction", "market": "us", "symbol": "NVDA",
    }
    # qo 仅建会话,绝不成交
    assert not await _positions(db_session, acct.id)


@pytest.mark.asyncio
async def test_card_qk_returns_kline(db_session: AsyncSession):
    """🆕 P0-2:点行情卡「📈 K线」(qk)→ 返回 K 线回复。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 724)
    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 724, "qk:crypto:BTC/USDT",  # type: ignore[arg-type]
    )
    assert "BTC/USDT" in reply.text
    assert "K线" in reply.text


@pytest.mark.asyncio
async def test_bare_price_asks_then_bare_code_quotes(db_session: AsyncSession):
    """🆕 P0-3:裸 /price → 引导直接发代码(设 awaiting=quote)· 下一条裸代码直接查。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 725)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0), _bar(120.0)])
    ask = await router.handle_command(db_session, redis, ch, 725, "/price")  # type: ignore[arg-type]
    assert "直接发代码" in ask.text
    assert json.loads(redis._d["tg_session:725"]) == {"awaiting": "quote"}
    # 下一条裸代码 → 行情(走 awaiting 分支 · 市场自动判断)
    quote = await router.handle_command(db_session, redis, ch, 725, "600519")  # type: ignore[arg-type]
    assert "600519" in quote.text


# ── 扫库判定 + 大小写模糊 + 同名两边都出(本刀)─────────────────────────────


@pytest.mark.asyncio
async def test_bare_lowercase_crypto_resolves(db_session: AsyncSession):
    """🆕 问题①:裸 `btc` 扫到加密(带斜杠 spot 形态)· 不再被判美股查不到。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 730)
    ch = _FakeCH([_bar(100.0), _bar(120.0)], exists={("crypto", "BTC/USDT")})
    reply = await router.handle_command(db_session, _FakeRedis(), ch, 730, "btc")  # type: ignore[arg-type]
    assert "BTC/USDT" in reply.text
    flat = json.dumps(reply.keyboard, ensure_ascii=False)
    assert "qk:crypto:BTC/USDT" in flat  # 卡片 action = 带斜杠形态


@pytest.mark.asyncio
async def test_bare_lowercase_us_resolves(db_session: AsyncSession):
    """🆕 问题②:小写 `nvda` 经 upper 扫到美股 · 不再要求大写。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 731)
    ch = _FakeCH([_bar(100.0), _bar(120.0)], exists={("us", "NVDA")})
    reply = await router.handle_command(db_session, _FakeRedis(), ch, 731, "nvda")  # type: ignore[arg-type]
    assert "NVDA" in reply.text
    assert "qk:us:NVDA" in json.dumps(reply.keyboard, ensure_ascii=False)


@pytest.mark.asyncio
async def test_same_name_both_markets_multi_crypto_first(db_session: AsyncSession):
    """🆕 同名两边都中 → handle_command_multi 返回【两条】· 加密在前、美股在后。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 732)
    ch = _FakeCH(
        [_bar(100.0), _bar(120.0)],
        exists={("crypto", "AAA/USDT"), ("us", "AAA")},
    )
    out = await router.handle_command_multi(db_session, _FakeRedis(), ch, 732, "aaa")  # type: ignore[arg-type]
    assert len(out) == 2  # noqa: PLR2004
    first = json.dumps(out[0].keyboard, ensure_ascii=False)
    second = json.dumps(out[1].keyboard, ensure_ascii=False)
    assert "qk:crypto:AAA/USDT" in first  # 加密在前
    assert "qk:us:AAA" in second          # 美股在后


@pytest.mark.asyncio
async def test_single_hit_multi_is_one_message(db_session: AsyncSession):
    """🆕 单命中 → handle_command_multi 返回单元素列表(transport 单条零回归)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 733)
    ch = _FakeCH([_bar(100.0), _bar(120.0)], exists={("us", "NVDA")})
    out = await router.handle_command_multi(db_session, _FakeRedis(), ch, 733, "NVDA")  # type: ignore[arg-type]
    assert len(out) == 1
    assert "qk:us:NVDA" in json.dumps(out[0].keyboard, ensure_ascii=False)


@pytest.mark.asyncio
async def test_bare_code_no_hit_suggests_slash(db_session: AsyncSession):
    """🆕 字母代码两库都未命中 → 提示带斜杠加密形态(不静默 not_found)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 734)
    ch = _FakeCH([], exists=set())  # 啥都不命中
    reply = await router.handle_command(db_session, _FakeRedis(), ch, 734, "zzz")  # type: ignore[arg-type]
    assert "未找到" in reply.text
    assert "ZZZ/USDT" in reply.text  # 带斜杠提示(已 upper)


@pytest.mark.asyncio
async def test_pure_digit_skips_scan_single(db_session: AsyncSession):
    """🆕 纯数字(6位 cn)→ 单条 · 不走扫库(exists 为空也能查到 = 没调 symbol_exists)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 735)
    ch = _FakeCH([_bar(100.0), _bar(120.0)], exists=set())  # 空 exists
    out = await router.handle_command_multi(db_session, _FakeRedis(), ch, 735, "600519")  # type: ignore[arg-type]
    assert len(out) == 1
    assert "600519" in out[0].text
    assert "qk:cn:600519" in json.dumps(out[0].keyboard, ensure_ascii=False)


# ── 本刀:中文名搜索 + 无K线轻量卡 + qv 候选点击 ─────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("茅台", True),
        ("贵州茅台", True),
        ("腾讯", True),
        ("茅台600", True),      # 中文+数字混合也算名称
        ("NVDA", False),         # 字母代码 → 上游 detect 处理
        ("btc", False),
        ("600519", False),       # 纯数字 → 上游处理
        ("BTC/USDT", False),
        ("hello world", False),  # 英文句子(全 ASCII)→ build_hint
        ("", False),
        ("   ", False),
        ("/menu", False),        # 命令
    ],
)
def test_looks_like_name(text: str, expected: bool):  # noqa: FBT001
    assert router._looks_like_name(text) is expected


@pytest.mark.asyncio
async def test_chinese_name_single_hit_quotes(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """🆕 中文名单命中(有 kline)→ 直接完整行情卡。"""
    from app.services.bot.query import NameHit

    user = await make_user(db_session)
    await _bind(db_session, user.id, 743)

    async def _fake_search(_ch: object, _raw: str, limit: int = 8) -> list[NameHit]:  # noqa: ARG001
        return [NameHit(market="cn", symbol="600519", name="贵州茅台")]

    monkeypatch.setattr(router, "search_by_name", _fake_search)
    ch = _FakeCH([_bar(100.0), _bar(120.0)])  # 茅台有 kline → 完整卡
    reply = await router.handle_command(db_session, _FakeRedis(), ch, 743, "茅台")  # type: ignore[arg-type]
    assert "600519" in reply.text
    assert "qk:cn:600519" in json.dumps(reply.keyboard, ensure_ascii=False)


@pytest.mark.asyncio
async def test_chinese_name_multi_hit_candidate_list(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """🆕 中文名多命中 → 候选列表(单条卡 + qv 按钮 · 不需多条 transport)。"""
    from app.services.bot.query import NameHit

    user = await make_user(db_session)
    await _bind(db_session, user.id, 744)

    async def _fake_search(_ch: object, _raw: str, limit: int = 8) -> list[NameHit]:  # noqa: ARG001
        return [
            NameHit(market="cn", symbol="600036", name="招商银行"),
            NameHit(market="hk", symbol="00700", name="腾讯控股"),
        ]

    monkeypatch.setattr(router, "search_by_name", _fake_search)
    reply = await router.handle_command(db_session, _FakeRedis(), _FakeCH(), 744, "银行")  # type: ignore[arg-type]
    assert "点选" in reply.text
    flat = json.dumps(reply.keyboard, ensure_ascii=False)
    assert "qv:cn:600036" in flat
    assert "qv:hk:00700" in flat


@pytest.mark.asyncio
async def test_chinese_name_no_hit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """🆕 中文名 0 命中 → 友好未找到(不含加密斜杠提示)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 745)

    async def _fake_search(_ch: object, _raw: str, limit: int = 8) -> list:  # noqa: ARG001
        return []

    monkeypatch.setattr(router, "search_by_name", _fake_search)
    reply = await router.handle_command(db_session, _FakeRedis(), _FakeCH(), 745, "查无此名")  # type: ignore[arg-type]
    assert "未找到" in reply.text


@pytest.mark.asyncio
async def test_qv_cn_no_kline_shows_lite_card(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """🆕 候选点击 qv:(cn/hk 无 kline 但 spot 有)→ 轻量卡 · 诚实标注无K线 · 无下单按钮。"""
    from datetime import UTC, datetime

    from app.services.bot.query import SpotLite

    user = await make_user(db_session)
    await _bind(db_session, user.id, 746)

    async def _fake_lite(_ch: object, market: str, symbol: str) -> SpotLite:
        return SpotLite(
            market=market, symbol=symbol, name="长尾港股", last_price=12.3,
            change_pct=2.1, amount=1.5e8, ts=datetime(2026, 6, 15, 4, 30, tzinfo=UTC),
        )

    monkeypatch.setattr(router, "get_spot_lite", _fake_lite)
    ch = _FakeCH([])  # 无 kline → query_symbol None → 走 lite
    reply = await router.handle_callback(db_session, _FakeRedis(), ch, 746, "qv:hk:00700")  # type: ignore[arg-type]
    assert "暂无 K线" in reply.text
    assert "长尾港股" in reply.text
    flat = json.dumps(reply.keyboard, ensure_ascii=False)
    assert "网页查看" in flat
    assert "qo:" not in flat  # ★轻量卡不放下单
    assert "qk:" not in flat  # 也不放 K线(本就无)


@pytest.mark.asyncio
async def test_qv_with_kline_full_card(db_session: AsyncSession):
    """🆕 qv:(有 kline)→ 完整行情卡(qk/qo/qr 按钮)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 747)
    ch = _FakeCH([_bar(100.0), _bar(120.0)])
    reply = await router.handle_callback(db_session, _FakeRedis(), ch, 747, "qv:cn:600519")  # type: ignore[arg-type]
    assert "600519" in reply.text
    assert "qk:cn:600519" in json.dumps(reply.keyboard, ensure_ascii=False)


@pytest.mark.asyncio
async def test_quote_or_lite_crypto_us_no_regression(db_session: AsyncSession):
    """🆕 crypto/us 无 kline → 仍 build_symbol_not_found(永不进 lite · 零回归)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, 748)
    ch = _FakeCH([])  # 无 kline
    reply = await router.handle_callback(db_session, _FakeRedis(), ch, 748, "qr:us:NVDA")  # type: ignore[arg-type]
    assert "未找到" in reply.text  # 不是轻量卡
