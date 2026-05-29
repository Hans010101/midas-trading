"""Bot 入站编排 · 0025 M1-G G3 + G4(下单)+ ADR 0032 多通道地基。

通道中立核心 `handle_inbound(InboundMessage) -> ReplyModel`:把【已验签】事件归一后的
入站路由到核心层(查询 / 下单),返回中立 ReplyModel(由各通道 renderer 渲染)。两类入站:
- kind=text:消息文本(非 /start 绑定)· /menu·/price·会话态续输代码
- kind=button:inline 按钮 / 卡片回调(action)

Telegram 适配 `handle_command` / `handle_callback`:构造 InboundMessage → handle_inbound →
render_for_telegram,保持原 BotReply 出参(webhook + 旧测试零改动)。飞书(P3)将另起
webhook 直接构造 InboundMessage 调 handle_inbound + 自己的 renderer。

🔴 红线(R1):user_id【只】从 resolve_user_id(channel, channel_uid) 取(已验签事件的
channel_uid)· 绝不信任消息文本 / 会话里的任何身份信息。下单确认时 user_id 仍从 channel_uid
重新解析(会话只存「下什么」,不存身份)。未绑定 → 引导绑定。
DP11 限流:命令(含回调)≤20/min、下单 ≤10/min(per-uid · 顶部拦截)。
危险操作(下单)必经二次确认按钮(ordok/ordno),不能一点即成交。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.alert_rule import AlertRule
from app.services.alerts.recommended import apply_recommended_rules
from app.services.bot import order as order_mod
from app.services.bot import quiet as quiet_mod
from app.services.bot import ratelimit, replies
from app.services.bot.identity import resolve_user_id
from app.services.bot.query import (
    query_alert_rules,
    query_positions,
    query_symbol,
    query_watchlist,
)
from app.services.bot.renderers.telegram import render_for_telegram
from app.services.bot.replies import InboundMessage, ReplyModel
from app.services.bot.session import clear_session, get_session, set_session

if TYPE_CHECKING:
    from uuid import UUID

    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.bot.renderers.telegram import BotReply
    from app.services.clickhouse_client import ClickHouseClient

_CN_CODE_LEN = 6
_ASK_PARTS = 3  # ask:<intent>:<market>
_VALID_MARKETS = {"cn", "us", "crypto"}


def _guess_market(symbol: str) -> str:
    """从代码形态猜市场:含斜杠→crypto,6 位纯数字→cn,其余→us。"""
    s = symbol.strip().upper()
    if "/" in s:
        return "crypto"
    if s.isdigit() and len(s) == _CN_CODE_LEN:
        return "cn"
    return "us"


async def _do_quote(ch: ClickHouseClient, market: str, symbol: str) -> ReplyModel:
    quote = await query_symbol(ch, market, symbol)
    if quote is None:
        return replies.build_symbol_not_found(market, symbol)
    return replies.build_quote(quote)


# ── 通道中立核心 ──────────────────────────────────────────────────────


async def handle_inbound(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    msg: InboundMessage,
) -> ReplyModel:
    """通道中立入站编排 · 入站 InboundMessage → 出站 ReplyModel。

    阶段一只接 telegram(channel_uid 即 chat_id,数字);飞书 / 钉钉(P2/P3)接入时
    会把 session / ratelimit 的键改为按 (channel, channel_uid) 命名,届时去掉 int() 假设。
    """
    chat_id = int(msg.channel_uid)  # 阶段一:telegram channel_uid == chat_id
    if msg.kind == "text":
        return await _handle_text(db, redis, ch, msg.channel, chat_id, msg.text)
    return await _handle_button(db, redis, ch, msg.channel, chat_id, msg.action)


async def _handle_text(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    channel: str,
    chat_id: int,
    text: str | None,
) -> ReplyModel:
    """消息文本入口(非 /start 绑定)· 返回中立 ReplyModel。"""
    if not await ratelimit.allow_command(redis, chat_id):
        return replies.build_rate_limited()
    user_id = await resolve_user_id(db, channel, str(chat_id))
    if user_id is None:
        return replies.build_not_bound()

    body = (text or "").strip()

    # /menu 或裸 /start → 主菜单
    if body in {"/menu", "/start"} or body.startswith("/start@"):
        await clear_session(redis, chat_id)
        return replies.build_main_menu()

    # /price <代码> → 直接查行情(自动猜市场)
    if body.startswith("/price"):
        parts = body.split(maxsplit=1)
        if len(parts) < 2:  # noqa: PLR2004
            return replies.build_market_picker("quote")
        symbol = parts[1].strip()
        await clear_session(redis, chat_id)
        return await _do_quote(ch, _guess_market(symbol), symbol)

    # 会话态续输代码
    sess = await get_session(redis, chat_id)
    if sess and sess.get("awaiting") in {"quote", "kline"}:
        symbol = body
        market = str(sess.get("market") or _guess_market(symbol))
        intent = str(sess["awaiting"])
        await clear_session(redis, chat_id)
        if not symbol:
            return replies.build_ask_symbol(intent, market)
        if intent == "kline":
            return replies.build_kline_link(market, symbol)
        return await _do_quote(ch, market, symbol)

    # 下单流程:之前点了「下单 → 选市场」,正在等代码 → 规范化 + 校验 → 方向选择
    if sess and sess.get("step") == "order_symbol":
        raw = body
        market = str(sess.get("market") or _guess_market(raw))
        if not raw:
            return replies.build_order_ask_symbol(market)
        # #296 改动二:规范化(大小写无关 + 简称/缺斜杠)+ 存在性校验(crypto 走 perp mark)
        canonical = order_mod.normalize_symbol(market, raw)
        price = (
            await order_mod.quote_price(ch, market, canonical) if canonical else None
        )
        if not canonical or price is None:
            # 不静默继续(原会走到撮合才报"无报价")· 直接提示重输 · session 仍停 order_symbol
            return replies.build_order_symbol_invalid(market, raw)
        await set_session(
            redis, chat_id,
            {"step": "order_direction", "market": market, "symbol": canonical},
        )
        return replies.build_order_directions(market, canonical, float(price))

    # 选方向那步误输文字 → 友好引导(标的已选 · session 不清 · 上条方向按钮仍可点)·
    # 不再落到泛化 build_hint(把人推回主菜单)
    if sess and sess.get("step") == "order_direction":
        return replies.build_order_direction_hint()

    # 其它文本 → 提示
    return replies.build_hint()


async def _handle_button(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    channel: str,
    chat_id: int,
    data: str | None,
) -> ReplyModel:
    """inline 按钮 / 卡片回调入口 · 返回中立 ReplyModel(TG 用 editMessageText 原地刷新)。"""
    if not await ratelimit.allow_command(redis, chat_id):
        return replies.build_rate_limited()
    user_id = await resolve_user_id(db, channel, str(chat_id))
    if user_id is None:
        return replies.build_not_bound()

    d = (data or "").strip()

    if d == "menu:main":
        await clear_session(redis, chat_id)
        return replies.build_main_menu()
    if d == "menu:quote":
        await clear_session(redis, chat_id)
        return replies.build_market_picker("quote")
    if d == "menu:kline":
        await clear_session(redis, chat_id)
        return replies.build_market_picker("kline")
    if d.startswith("ask:"):
        parts = d.split(":")
        if len(parts) == _ASK_PARTS:
            _, intent, market = parts
            await set_session(redis, chat_id, {"awaiting": intent, "market": market})
            return replies.build_ask_symbol(intent, market)
        return replies.build_main_menu()
    if d == "act:watchlist":
        wl_rows = await query_watchlist(db, ch, user_id)
        return replies.build_watchlist(wl_rows)
    if d == "act:positions":
        pos_rows = await query_positions(db, user_id)
        return replies.build_positions(pos_rows)
    # ── 告警规则(G5 · 查看 / 启停 / 一键推荐)─────────────────────────
    if d == "menu:rules":
        await clear_session(redis, chat_id)
        return replies.build_alert_rules(await query_alert_rules(db, user_id))
    if d.startswith("rules:toggle:"):
        return await _handle_rule_toggle(db, user_id, d)
    if d == "rules:apply":
        created, skipped = await apply_recommended_rules(db, user_id)
        note = f"已应用推荐:新增 {created} 条 · 跳过 {skipped} 条"
        return replies.build_alert_rules(await query_alert_rules(db, user_id), note=note)

    # ── 安静时段(N3 · 查看 + 启停 + 起止小时步进 · 时区切换留网页 DP9)────
    # 🔴 R1 隔离:user_id 来自顶部 resolve_user_id(channel, channel_uid) · 所有 quiet_mod
    #    调用都用同一 user_id;quiet_mod 模块层不接受 chat_id / 其他 id · 物理上改不到别人的 config
    if d == "menu:quiet":
        await clear_session(redis, chat_id)
        view = await quiet_mod.load_quiet_hours(db, user_id)
        return replies.build_quiet_hours(view)
    if d == "quiet:toggle":
        view = await quiet_mod.toggle_enabled(db, user_id)
        return replies.build_quiet_hours(view)
    if d == "quiet:s+":
        view = await quiet_mod.step_start_hour(db, user_id, +1)
        return replies.build_quiet_hours(view)
    if d == "quiet:s-":
        view = await quiet_mod.step_start_hour(db, user_id, -1)
        return replies.build_quiet_hours(view)
    if d == "quiet:e+":
        view = await quiet_mod.step_end_hour(db, user_id, +1)
        return replies.build_quiet_hours(view)
    if d == "quiet:e-":
        view = await quiet_mod.step_end_hour(db, user_id, -1)
        return replies.build_quiet_hours(view)
    if d == "quiet:noop":
        # 中间显示时间的按钮 · 点了不做事,只重渲(用户体验上是"占位")
        view = await quiet_mod.load_quiet_hours(db, user_id)
        return replies.build_quiet_hours(view)

    # ── 下单流程(G4 · 虚拟 · 必经二次确认)──────────────────────────
    if d == "menu:order":
        await clear_session(redis, chat_id)
        return replies.build_order_market_picker()
    if d.startswith("omkt:"):
        market = d.split(":", 1)[1]
        if market not in _VALID_MARKETS:
            return replies.build_main_menu()
        await set_session(redis, chat_id, {"step": "order_symbol", "market": market})
        return replies.build_order_ask_symbol(market)
    if d.startswith("odir:"):
        return await _handle_direction(db, redis, ch, chat_id, user_id, d.split(":", 1)[1])
    if d == "ordok":
        return await _handle_confirm(db, redis, ch, chat_id, user_id)
    if d == "ordno":
        await clear_session(redis, chat_id)
        return replies.build_order_cancelled()

    # 未知回调兜底
    return replies.build_main_menu()


async def _handle_direction(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    chat_id: int,
    user_id: UUID,
    direction: str,
) -> ReplyModel:
    """选了方向 → 生成预览 + 进入确认态(会话只存意图,不存身份)。"""
    sess = await get_session(redis, chat_id)
    if not sess or sess.get("step") != "order_direction":
        return replies.build_main_menu()
    market = str(sess.get("market") or "")
    symbol = str(sess.get("symbol") or "")
    if not symbol or not order_mod.direction_valid(market, direction):
        return replies.build_main_menu()
    intent = order_mod.OrderIntent(market=market, symbol=symbol, direction=direction)
    preview = await order_mod.build_preview(ch, db, user_id, intent)
    if preview is None:
        await clear_session(redis, chat_id)
        return replies.build_order_unavailable()
    await set_session(
        redis, chat_id,
        {"step": "order_confirm", "market": market, "symbol": symbol, "direction": direction},
    )
    return replies.build_order_preview(preview)


async def _handle_confirm(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    chat_id: int,
    user_id: UUID,
) -> ReplyModel:
    """点了「确认下单」→ 执行虚拟下单。

    🔴 user_id 是本函数入参(由上游从已验签 channel_uid 解析),会话里【没有】身份 ——
    下单永远只作用于绑定账号。下单限流在此计配额。二次确认必经:仅当会话处于
    order_confirm(由 _handle_direction 写入)才执行,任何通道都无法跳过。
    """
    sess = await get_session(redis, chat_id)
    if not sess or sess.get("step") != "order_confirm":
        return replies.build_main_menu()
    if not await ratelimit.allow_order(redis, chat_id):
        return replies.build_rate_limited()
    market = str(sess.get("market") or "")
    symbol = str(sess.get("symbol") or "")
    direction = str(sess.get("direction") or "")
    await clear_session(redis, chat_id)
    if not symbol or not order_mod.direction_valid(market, direction):
        return replies.build_main_menu()
    intent = order_mod.OrderIntent(market=market, symbol=symbol, direction=direction)
    result = await order_mod.execute(db, ch, user_id, intent)
    # #296 去重:成交走富回执(单条);拒单 / 异常回落原简版
    if result.filled and result.body:
        return replies.build_order_receipt(result.body)
    return replies.build_order_result(result.title, result.detail)


async def _handle_rule_toggle(db: AsyncSession, user_id: UUID, data: str) -> ReplyModel:
    """切换某条告警规则启停。

    🔴 ownership-scoped:按 (id, user_id) 查询,只能翻【自己】的规则 —— 跨用户无效
    (A 绝不能启停 B 的规则)· 与 G2b PATCH 同款归属校验。
    """
    parts = data.split(":")  # rules:toggle:{id}
    if len(parts) == _ASK_PARTS and parts[2].isdigit():
        rule = await db.scalar(
            select(AlertRule).where(
                AlertRule.id == int(parts[2]), AlertRule.user_id == user_id,
            ),
        )
        if rule is not None:
            rule.enabled = not rule.enabled
            await db.commit()
    return replies.build_alert_rules(await query_alert_rules(db, user_id))


# ── Telegram 适配(webhook + 旧测试入口 · 返回 BotReply · 行为零回归)──────


async def handle_command(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    chat_id: int,
    text: str | None,
) -> BotReply:
    """Telegram 文本入口 · 归一为 InboundMessage → 核心 → 渲染回 BotReply。"""
    msg = InboundMessage(
        channel="telegram", channel_uid=str(chat_id), kind="text", text=text,
    )
    return render_for_telegram(await handle_inbound(db, redis, ch, msg))


async def handle_callback(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    chat_id: int,
    data: str | None,
) -> BotReply:
    """Telegram 回调入口 · 归一为 InboundMessage → 核心 → 渲染回 BotReply。"""
    msg = InboundMessage(
        channel="telegram", channel_uid=str(chat_id), kind="button", action=data,
    )
    return render_for_telegram(await handle_inbound(db, redis, ch, msg))
