"""Bot 入站编排(Telegram 适配层)· 0025 M1-G G3。

把【已验证】webhook 的命令 / 按钮回调路由到核心层查询,再选渲染。两条入口:
- handle_command:消息文本(非 /start 绑定)· /menu·/price·会话态续输代码
- handle_callback:inline 按钮回调(callback_query.data)

🔴 红线(R1):user_id【只】从 identity.resolve_user_id(chat_id) 取(已验证 webhook 的
chat.id),自选 / 持仓查询都用它 —— 绝不信任消息文本里的任何身份信息。未绑定 → 引导去
网页端绑定。一切输出带免责(由 telegram_ui 统一加尾)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.bot import telegram_ui as ui
from app.services.bot.identity import resolve_user_id
from app.services.bot.query import query_positions, query_symbol, query_watchlist
from app.services.bot.session import clear_session, get_session, set_session

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.bot.telegram_ui import BotReply
    from app.services.clickhouse_client import ClickHouseClient

_CN_CODE_LEN = 6
_ASK_PARTS = 3  # ask:<intent>:<market>


def _guess_market(symbol: str) -> str:
    """从代码形态猜市场:含斜杠→crypto,6 位纯数字→cn,其余→us。"""
    s = symbol.strip().upper()
    if "/" in s:
        return "crypto"
    if s.isdigit() and len(s) == _CN_CODE_LEN:
        return "cn"
    return "us"


async def _do_quote(ch: ClickHouseClient, market: str, symbol: str) -> BotReply:
    quote = await query_symbol(ch, market, symbol)
    if quote is None:
        return ui.render_symbol_not_found(market, symbol)
    return ui.render_quote(quote)


async def handle_command(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    chat_id: int,
    text: str | None,
) -> BotReply:
    """消息文本入口(非 /start 绑定)· 返回结构化回复。"""
    user_id = await resolve_user_id(db, chat_id)
    if user_id is None:
        return ui.render_not_bound()

    body = (text or "").strip()

    # /menu 或裸 /start → 主菜单
    if body in {"/menu", "/start"} or body.startswith("/start@"):
        await clear_session(redis, chat_id)
        return ui.render_main_menu()

    # /price <代码> → 直接查行情(自动猜市场)
    if body.startswith("/price"):
        parts = body.split(maxsplit=1)
        if len(parts) < 2:  # noqa: PLR2004
            return ui.render_market_picker("quote")
        symbol = parts[1].strip()
        await clear_session(redis, chat_id)
        return await _do_quote(ch, _guess_market(symbol), symbol)

    # 会话态:之前点了「行情/K线」按钮、正在等代码
    sess = await get_session(redis, chat_id)
    if sess and sess.get("awaiting") in {"quote", "kline"}:
        symbol = body
        market = str(sess.get("market") or _guess_market(symbol))
        intent = str(sess["awaiting"])
        await clear_session(redis, chat_id)
        if not symbol:
            return ui.render_ask_symbol(intent, market)
        if intent == "kline":
            return ui.render_kline_link(market, symbol)
        return await _do_quote(ch, market, symbol)

    # 其它文本 → 提示
    return ui.render_hint()


async def handle_callback(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    chat_id: int,
    data: str | None,
) -> BotReply:
    """inline 按钮回调入口 · 返回结构化回复(webhook 用 editMessageText 原地刷新)。"""
    user_id = await resolve_user_id(db, chat_id)
    if user_id is None:
        return ui.render_not_bound()

    d = (data or "").strip()

    if d == "menu:main":
        await clear_session(redis, chat_id)
        return ui.render_main_menu()
    if d == "menu:quote":
        await clear_session(redis, chat_id)
        return ui.render_market_picker("quote")
    if d == "menu:kline":
        await clear_session(redis, chat_id)
        return ui.render_market_picker("kline")
    if d.startswith("ask:"):
        parts = d.split(":")
        if len(parts) == _ASK_PARTS:
            _, intent, market = parts
            await set_session(redis, chat_id, {"awaiting": intent, "market": market})
            return ui.render_ask_symbol(intent, market)
        return ui.render_main_menu()
    if d == "act:watchlist":
        wl_rows = await query_watchlist(db, ch, user_id)
        return ui.render_watchlist(wl_rows)
    if d == "act:positions":
        pos_rows = await query_positions(db, user_id)
        return ui.render_positions(pos_rows)
    if d == "stub:order":
        return ui.render_order_stub()
    if d == "stub:rules":
        return ui.render_rules_stub()

    # 未知回调兜底
    return ui.render_main_menu()
