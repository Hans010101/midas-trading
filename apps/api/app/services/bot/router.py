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
    crypto_has_realtime_kline,
    detect_symbol_markets,
    get_spot_lite,
    query_alert_rules,
    query_positions,
    query_symbol,
    query_watchlist,
    search_by_name,
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
_HK_CODE_LEN = 5  # 港股代码 5 位(00700 / 09988)
_ASK_PARTS = 3  # ask:<intent>:<market>
_SYM_ACTION_PARTS = 3  # <op>:<market>:<symbol>(行情卡就地操作 qk/qo/qr)
_MAX_SYMBOL_LEN = 15  # 疑似代码的最大长度(防把长句当代码)
_VALID_MARKETS = {"cn", "us", "crypto", "hk"}
_SYM_OPS = {"qk", "qo", "qr", "qv"}  # 行情卡就地操作:看K线 / 下单 / 刷新 / 查看(候选点击)
# 疑似代码允许的字符:字母 + 数字 + 斜杠(crypto BTC/USDT)· 不含空格 / 冒号 / 中文
_SYMBOL_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/",
)

# ── 常驻快捷键盘(reply keyboard · P1)──────────────────────────────────────
# 按钮文字 → 动作(精确 dispatch · ★必须在 _looks_like_symbol / _looks_like_name 之前拦截,
# 否则中文按钮文字会被中文名搜索当股票名搜)。__quote_ask/__kline_ask 是内部哨兵(非 callback)。
_REPLY_KB_ACTIONS: dict[str, str] = {
    "📊 行情": "__quote_ask",
    "📈 K线": "__kline_ask",
    "💼 持仓": "act:positions",
    "⭐ 自选": "act:watchlist",
    "🛒 下单": "menu:order",
    "☰ 菜单": "menu:main",
}
# TG sendMessage 的 reply_markup(常驻键盘 · 设一次后输入框上方常驻;布局 3 行 × 2)·
# transport(绑定成功 / /start)import 本常量发一条独立消息设置。labels 与 _REPLY_KB_ACTIONS 同源。
REPLY_KB_MARKUP: dict[str, object] = {
    "keyboard": [
        ["📊 行情", "📈 K线"],
        ["💼 持仓", "⭐ 自选"],
        ["🛒 下单", "☰ 菜单"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


def _guess_market(symbol: str) -> str:
    """从代码形态猜市场:含斜杠→crypto,6 位纯数字→cn,5 位纯数字→hk,其余→us。"""
    s = symbol.strip().upper()
    if "/" in s:
        return "crypto"
    if s.isdigit() and len(s) == _CN_CODE_LEN:
        return "cn"
    if s.isdigit() and len(s) == _HK_CODE_LEN:
        return "hk"
    return "us"


def _looks_like_symbol(text: str) -> bool:
    """无会话自由文本是否疑似【一个标的代码】(单 token · 纯函数 · 可单测)。

    判定(全满足):strip 后非空、无空格、长度 ≤15、仅字母/数字/斜杠、不以 "/" 开头
    (命令 /menu·/price 已被上方分支拦掉,这里再防一道)。多 token / 含空格 / 像句子
    (含中文标点等非允许字符)→ False,落 build_hint(把人推回菜单)。
    """
    s = text.strip()
    if not s or len(s) > _MAX_SYMBOL_LEN:
        return False
    if s.startswith("/") or " " in s:
        return False
    return set(s) <= _SYMBOL_CHARS


def _looks_like_name(text: str) -> bool:
    """是否像【名称类】搜索词(中文名等)· 纯函数 · 可单测。

    判据:strip 后非空、不以 / 开头(非命令)、含至少一个非 ASCII 字符(中文等)。
    纯数字 / 字母代码已被上游分支处理;英文句子(全 ASCII)落 build_hint,不当名称搜。
    """
    s = text.strip()
    if not s or s.startswith("/"):
        return False
    return not s.isascii()


def _parse_sym_action(d: str) -> tuple[str, str, str] | None:
    """解析行情卡就地操作回调 `<op>:<market>:<symbol>`(P0-2 · qk/qo/qr)。

    split(":", 2):op / market / symbol —— symbol 自身可含斜杠(crypto BTC/USDT)但不含
    冒号,故三段切分安全(crypto 去斜杠后亦无特殊字符)。op∈qk/qo/qr、market∈_VALID_MARKETS、
    symbol 非空才有效,否则 None(交给后续分支 / 兜底)。
    """
    parts = d.split(":", 2)
    if len(parts) != _SYM_ACTION_PARTS:
        return None
    op, market, symbol = parts
    if op not in _SYM_OPS or market not in _VALID_MARKETS or not symbol:
        return None
    return op, market, symbol


async def _quote_or_lite(ch: ClickHouseClient, market: str, symbol: str) -> ReplyModel:
    """统一出卡:有 kline → 完整行情卡;cn/hk 无 kline 但 spot 有 → 轻量卡;否则未找到。

    crypto/us 永不进 lite 分支(它们走自己的 kline 路径)→ 与原 _do_quote 行为完全一致(零回归)。
    cn/hk 长尾(spot 有 / kline 未采)从「未找到」升级为轻量信息卡(诚实标注无深度数据)。
    """
    quote = await query_symbol(ch, market, symbol)
    if quote is not None:
        # crypto:有实时 15m kline(主流 5 币)→ 完整卡;否则(TRX 等长尾)→ 加密轻量卡
        # (ticker 价 + perp 指标 · 诚实标无实时K线 · 可下单)。cn/us 维持完整卡。
        if market == "crypto" and not await crypto_has_realtime_kline(ch, symbol):
            return replies.build_crypto_lite_card(quote)
        return replies.build_quote(quote)
    if market in ("cn", "hk"):
        lite = await get_spot_lite(ch, market, symbol)
        if lite is not None:
            return replies.build_lite_quote_card(lite)
    return replies.build_symbol_not_found(market, symbol)


# ── 通道中立核心 ──────────────────────────────────────────────────────


async def handle_inbound_multi(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    msg: InboundMessage,
) -> list[ReplyModel]:
    """通道中立入站编排(多条版)· text → ReplyModel 列表(裸字母命中多市场 → 多张卡 · 加密在前);
    button → 单张包成 [x]。TG webhook 走本入口逐条发;单条入口 handle_inbound 取首条。

    ADR 0032 阶段三:session / ratelimit 按 (channel, channel_uid) 键控 · channel_uid 是字符串
    (TG=chat_id 串、飞书=open_id),通道无关。
    """
    if msg.kind == "text":
        return await _handle_text(db, redis, ch, msg.channel, msg.channel_uid, msg.text)
    return [await _handle_button(db, redis, ch, msg.channel, msg.channel_uid, msg.action)]


async def handle_inbound(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    msg: InboundMessage,
) -> ReplyModel:
    """通道中立入站编排(单条 · 向后兼容飞书 + 旧测试)· 取首条 ReplyModel。

    单条路径(button / 单命中 text)首条即唯一;「裸字母命中多市场」的多条由 handle_inbound_multi +
    TG handle_command_multi 走,本单条入口取加密优先的首条(飞书侧零回归 · 飞书暂不做多卡)。
    """
    return (await handle_inbound_multi(db, redis, ch, msg))[0]


async def _quote_code_replies(ch: ClickHouseClient, body: str) -> list[ReplyModel]:
    """裸代码 → 行情卡列表(P0 升级:扫库判定 + 大小写模糊 + 同名两边都出)。

    · 纯数字(6位 cn / 5位 hk / 其余 us)→ _guess_market 单条(原样)。
    · 字母代码 → detect_symbol_markets 扫库(统一 upper):命中即出、加密+美股都中就【都出】
      (多条 · 加密在前);均未命中 → build_code_not_found(带斜杠提示)。
    crypto 命中用带斜杠 spot 形态 / us 用大写 —— 由 detect 统一产出,_do_quote 直接可查。
    """
    s = body.strip()
    if s.isdigit():
        return [await _quote_or_lite(ch, _guess_market(s), s)]
    hits = await detect_symbol_markets(ch, s)
    if not hits:
        return [replies.build_code_not_found(s)]
    return [await _quote_or_lite(ch, market, sym) for market, sym in hits]


async def _resolve_free_text_replies(
    ch: ClickHouseClient, body: str,
) -> list[ReplyModel]:
    """自由文本 → 行情卡列表(市场自动识别):字母/数字代码扫库 · 中文名搜索 · 否则提示。

    无会话裸文本、裸 /price 续输、reply-kb [行情] 续输【共用】本逻辑 —— 打代码或中文名都自动
    识别市场出卡(代码:detect 扫库 crypto+us / 数字 cn-hk;名称:search_by_name cn+hk)。
    """
    if _looks_like_symbol(body):
        return await _quote_code_replies(ch, body)
    if _looks_like_name(body):
        hits = await search_by_name(ch, body)
        if not hits:
            return [replies.build_name_not_found(body)]
        if len(hits) == 1:
            return [await _quote_or_lite(ch, hits[0].market, hits[0].symbol)]
        return [replies.build_candidate_list(hits)]
    return [replies.build_hint()]


async def _handle_text(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    channel: str,
    uid: str,
    text: str | None,
) -> list[ReplyModel]:
    """消息文本入口(非绑定)· 返回中立 ReplyModel【列表】。

    绝大多数路径单条([x]);仅「无会话裸【字母】代码同时命中加密 + 美股」返回多条(加密在前)·
    由 TG handle_command_multi 逐条发;单条入口 handle_inbound 取首条(飞书 / 旧测试零回归)。
    """
    if not await ratelimit.allow_command(redis, channel, uid):
        return [replies.build_rate_limited()]
    user_id = await resolve_user_id(db, channel, uid)
    if user_id is None:
        return [replies.build_not_bound()]

    body = (text or "").strip()

    # 常驻快捷键盘(reply keyboard)精确 dispatch · ★必须在所有启发式分支(尤其 _looks_like_name
    # 中文名搜索)之前,否则中文按钮文字会被当股票名搜(已确认坑)· 统一 clear_session = 干净切换。
    if body in _REPLY_KB_ACTIONS:
        await clear_session(redis, channel, uid)
        target = _REPLY_KB_ACTIONS[body]
        if target == "__quote_ask":
            # [行情] 不设 awaiting 会绕过名称搜索;设 awaiting=quote(无市场)· 续输走全检测分支
            await set_session(redis, channel, uid, {"awaiting": "quote"})
            return [replies.build_quote_ask()]
        if target == "__kline_ask":
            await set_session(redis, channel, uid, {"awaiting": "kline"})
            return [replies.build_kline_ask()]
        # [持仓]/[自选]/[下单]/[菜单] 复用现有 inline 处理器(reply-kb 点击=文本,故在此转发)
        return [await _handle_button(db, redis, ch, channel, uid, target)]

    # /menu 或裸 /start → 主菜单
    if body in {"/menu", "/start"} or body.startswith("/start@"):
        await clear_session(redis, channel, uid)
        return [replies.build_main_menu()]

    # /price <代码> → 扫库查行情(裸字母命中多市场 → 多条);裸 /price 无参 → 引导
    if body.startswith("/price"):
        parts = body.split(maxsplit=1)
        if len(parts) < 2:  # noqa: PLR2004
            # P0-3:裸 /price 不强制点市场 · 设 awaiting=quote · 下条裸代码走 awaiting 分支查。
            await set_session(redis, channel, uid, {"awaiting": "quote"})
            return [replies.build_quote_ask()]
        await clear_session(redis, channel, uid)
        return await _quote_code_replies(ch, parts[1].strip())

    # 会话态续输代码(★ 大小写兜底:us 大写存储 / crypto 带斜杠大写 · 用户小写直输也能命中)
    sess = await get_session(redis, channel, uid)
    if sess and sess.get("awaiting") in {"quote", "kline"}:
        intent = str(sess["awaiting"])
        chosen = sess.get("market")  # inline 选过市场则非空;裸 /price · reply-kb[行情] 为空
        await clear_session(redis, channel, uid)
        if not body:
            return [replies.build_ask_symbol(intent, str(chosen or "us"))]
        if intent == "kline":
            sym = body.upper()
            return [replies.build_kline_link(str(chosen or _guess_market(sym)), sym)]
        # quote:已选市场 → 直接查该市场;未选(/price · [行情])→ 全检测(代码扫库 + 中文名搜索)
        if chosen:
            return [await _quote_or_lite(ch, str(chosen), body.upper())]
        return await _resolve_free_text_replies(ch, body)

    # 下单流程:之前点了「下单 → 选市场」,正在等代码 → 规范化 + 校验 → 方向选择
    if sess and sess.get("step") == "order_symbol":
        raw = body
        market = str(sess.get("market") or _guess_market(raw))
        if not raw:
            return [replies.build_order_ask_symbol(market)]
        # #296 改动二:规范化(normalize_symbol 已 upper · 大小写无关 + 简称/缺斜杠)+ 存在性校验
        canonical = order_mod.normalize_symbol(market, raw)
        price = (
            await order_mod.quote_price(ch, market, canonical) if canonical else None
        )
        if not canonical or price is None:
            # 不静默继续(原会走到撮合才报"无报价")· 直接提示重输 · session 仍停 order_symbol
            return [replies.build_order_symbol_invalid(market, raw)]
        await set_session(
            redis, channel, uid,
            {"step": "order_direction", "market": market, "symbol": canonical},
        )
        return [replies.build_order_directions(market, canonical, float(price))]

    # 选方向那步误输文字 → 友好引导(标的已选 · session 不清 · 上条方向按钮仍可点)·
    # 不再落到泛化 build_hint(把人推回主菜单)
    if sess and sess.get("step") == "order_direction":
        return [replies.build_order_direction_hint()]

    # 无会话自由文本 → 代码扫库(裸 btc/小写 nvda 自动识别)/ 中文名搜索 / 提示 · 清残留会话再查。
    await clear_session(redis, channel, uid)
    return await _resolve_free_text_replies(ch, body)


async def _handle_button(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    channel: str,
    uid: str,
    data: str | None,
) -> ReplyModel:
    """inline 按钮 / 卡片回调入口 · 返回中立 ReplyModel(TG 用 editMessageText 原地刷新)。"""
    if not await ratelimit.allow_command(redis, channel, uid):
        return replies.build_rate_limited()
    user_id = await resolve_user_id(db, channel, uid)
    if user_id is None:
        return replies.build_not_bound()

    d = (data or "").strip()

    if d == "menu:main":
        await clear_session(redis, channel, uid)
        return replies.build_main_menu()
    if d == "menu:quote":
        await clear_session(redis, channel, uid)
        return replies.build_market_picker("quote")
    if d == "menu:kline":
        await clear_session(redis, channel, uid)
        return replies.build_market_picker("kline")
    if d.startswith("ask:"):
        parts = d.split(":")
        if len(parts) == _ASK_PARTS:
            _, intent, market = parts
            await set_session(
                redis, channel, uid, {"awaiting": intent, "market": market},
            )
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
        await clear_session(redis, channel, uid)
        return replies.build_alert_rules(await query_alert_rules(db, user_id))
    if d.startswith("rules:toggle:"):
        return await _handle_rule_toggle(db, user_id, d)
    if d == "rules:apply":
        created, skipped = await apply_recommended_rules(db, user_id)
        note = f"已应用推荐:新增 {created} 条 · 跳过 {skipped} 条"
        return replies.build_alert_rules(await query_alert_rules(db, user_id), note=note)

    # ── 安静时段(N3 · 查看 + 启停 + 起止小时步进 · 时区切换留网页 DP9)────
    # 🔴 R1 隔离:user_id 来自顶部 resolve_user_id(channel, channel_uid) · 所有 quiet_mod
    #    调用都用同一 user_id;quiet_mod 模块层不接受 uid · 物理上改不到别人的 config
    if d == "menu:quiet":
        await clear_session(redis, channel, uid)
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

    # ── 行情卡就地操作(P0-2 · qk 看K线 / qo 直达下单 / qr 刷新 · 降链路)──────
    sym_action = _parse_sym_action(d)
    if sym_action is not None:
        return await _handle_sym_action(redis, ch, channel, uid, sym_action)

    # ── 下单流程(G4 · 虚拟 · 必经二次确认)──────────────────────────
    if d == "menu:order":
        await clear_session(redis, channel, uid)
        return replies.build_order_market_picker()
    if d.startswith("omkt:"):
        market = d.split(":", 1)[1]
        if market not in _VALID_MARKETS:
            return replies.build_main_menu()
        await set_session(
            redis, channel, uid, {"step": "order_symbol", "market": market},
        )
        return replies.build_order_ask_symbol(market)
    if d.startswith("odir:"):
        return await _handle_direction(
            db, redis, ch, channel, uid, user_id, d.split(":", 1)[1],
        )
    if d == "ordok":
        return await _handle_confirm(db, redis, ch, channel, uid, user_id)
    if d == "ordno":
        await clear_session(redis, channel, uid)
        return replies.build_order_cancelled()

    # 未知回调兜底
    return replies.build_main_menu()


async def _handle_sym_action(
    redis: Redis,
    ch: ClickHouseClient,
    channel: str,
    uid: str,
    parsed: tuple[str, str, str],
) -> ReplyModel:
    """行情卡【就地操作】回调:qk 看K线 / qr 刷新行情 / qo 直达下单(P0-2 · 降链路)。

    🔴 红线:qo 复用【现有】order_symbol→order_direction→confirm→ordok 链路(零新撮合)·
    身份不在此解析(下单确认时由 _handle_confirm 从 channel_uid 重新解析 · 会话只存「下什么」)。
    symbol 原样来自行情卡 action(= 上次 query_symbol 回显形态;crypto 带斜杠)· qr 据此精确复现
    原查询;qk 的 build_kline_link 内部对 crypto 去斜杠;qo 的 normalize_symbol 对 crypto 幂等。
    """
    op, market, symbol = parsed
    if op == "qk":
        return replies.build_kline_link(market, symbol)
    if op in ("qr", "qv"):
        # qr 刷新 / qv 候选点击查看 —— 同走统一出卡(有K线完整 / cn-hk 无K线轻量)
        return await _quote_or_lite(ch, market, symbol)
    # qo:卡片直达下单 —— 复用 order_symbol 之后的规范化 + 报价校验 + 进方向页(零新撮合)
    canonical = order_mod.normalize_symbol(market, symbol)
    price = await order_mod.quote_price(ch, market, canonical) if canonical else None
    if not canonical or price is None:
        return replies.build_order_symbol_invalid(market, symbol)
    await set_session(
        redis, channel, uid,
        {"step": "order_direction", "market": market, "symbol": canonical},
    )
    return replies.build_order_directions(market, canonical, float(price))


async def _handle_direction(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    channel: str,
    uid: str,
    user_id: UUID,
    direction: str,
) -> ReplyModel:
    """选了方向 → 生成预览 + 进入确认态(会话只存意图,不存身份)。"""
    sess = await get_session(redis, channel, uid)
    if not sess or sess.get("step") != "order_direction":
        return replies.build_main_menu()
    market = str(sess.get("market") or "")
    symbol = str(sess.get("symbol") or "")
    if not symbol or not order_mod.direction_valid(market, direction):
        return replies.build_main_menu()
    intent = order_mod.OrderIntent(market=market, symbol=symbol, direction=direction, source="bot")
    preview = await order_mod.build_preview(ch, db, user_id, intent)
    if preview is None:
        await clear_session(redis, channel, uid)
        return replies.build_order_unavailable()
    await set_session(
        redis, channel, uid,
        {"step": "order_confirm", "market": market, "symbol": symbol, "direction": direction},
    )
    return replies.build_order_preview(preview)


async def _handle_confirm(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    channel: str,
    uid: str,
    user_id: UUID,
) -> ReplyModel:
    """点了「确认下单」→ 执行虚拟下单。

    🔴 user_id 是本函数入参(由上游从已验签 channel_uid 解析),会话里【没有】身份 ——
    下单永远只作用于绑定账号。下单限流在此计配额。二次确认必经:仅当会话处于
    order_confirm(由 _handle_direction 写入)才执行,任何通道都无法跳过。
    """
    sess = await get_session(redis, channel, uid)
    if not sess or sess.get("step") != "order_confirm":
        return replies.build_main_menu()
    if not await ratelimit.allow_order(redis, channel, uid):
        return replies.build_rate_limited()
    market = str(sess.get("market") or "")
    symbol = str(sess.get("symbol") or "")
    direction = str(sess.get("direction") or "")
    await clear_session(redis, channel, uid)
    if not symbol or not order_mod.direction_valid(market, direction):
        return replies.build_main_menu()
    intent = order_mod.OrderIntent(market=market, symbol=symbol, direction=direction, source="bot")
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


async def handle_command_multi(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient,
    chat_id: int,
    text: str | None,
) -> list[BotReply]:
    """Telegram 文本入口(多条版)· 裸字母代码命中多市场 → 多张卡(加密在前)· webhook 逐条发。

    单命中 / 非代码文本 → 单元素列表(行为与 handle_command 一致)· 保证单条路径零回归。
    """
    msg = InboundMessage(
        channel="telegram", channel_uid=str(chat_id), kind="text", text=text,
    )
    return [
        render_for_telegram(r)
        for r in await handle_inbound_multi(db, redis, ch, msg)
    ]


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
