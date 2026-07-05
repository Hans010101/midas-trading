"""后端文案本地化表 · i18n Phase3(后端返本地化文本·前端零查表·决策C)。

★复用 validator.py 黄金范式:`{key: {zh, en}}` 表 + zh 恒等(zh 逐字节 = 今天的中文字面量)。
★不引 gettext/babel(全库零依赖)· 不复用前端 messages/*.json(跨进程读前端文件是坏耦合)。
★含运行时插值的文案用命名占位 `{name}` · translate(..., **params) 走 str.format。

刀1 只登记地基验证用的鉴权错误(deps · pre-auth 高价值);
刀2 补 C 端用户面错误 detail(~77)· 刀3 补规则层 label/reason(~54)· 逐刀扩表。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# {key: {"zh": 模板, "en": 模板}} · zh 为今天线上中文字面量【逐字节复刻】(zh 零变化铁证)。
_CATALOG: dict[str, dict[str, str]] = {
    # ── 刀1 · 鉴权层(pre-auth · 命中每个受保护/铂金请求)──────────────
    "auth.no_token": {
        "zh": "未携带 Bearer session token",
        "en": "No Bearer session token provided",
    },
    "auth.session_invalid": {
        "zh": "session 无效或已过期 · 请重新登录",
        "en": "Session invalid or expired · please sign in again",
    },
    "auth.account_disabled": {
        "zh": "账号已被停用",
        "en": "Account has been disabled",
    },
    "auth.platinum_required": {
        "zh": "需铂金权限",
        "en": "Platinum access required",
    },

    # ── 刀2 · C 端用户面错误 detail(zh 逐字节 = 今天线上字面量)────────────
    # 通用 · 跨文件复用
    "common.perp_only_crypto": {
        "zh": "instrument=perp 只支持 market=crypto · 当前 market={market}",
        "en": (
            "instrument=perp is only supported for market=crypto"
            " · current market={market}"
        ),
    },
    # 认证 / 账户 · account_disabled 复用上方刀1 key(同「账号已被停用」)
    "auth.age_not_confirmed": {
        "zh": "必须确认年满 18 周岁",
        "en": "You must confirm you are at least 18 years old",
    },
    "auth.email_taken": {
        "zh": "该邮箱已注册",
        "en": "This email is already registered",
    },
    "auth.invalid_credentials": {
        "zh": "邮箱或密码错误",
        "en": "Incorrect email or password",
    },
    "auth.email_not_verified": {
        "zh": "邮箱未验证 · 请查收注册邮件或调用 /resend-verification",
        "en": (
            "Email not verified · please check your registration email"
            " or call /resend-verification"
        ),
    },
    "auth.google_oauth_disabled": {
        "zh": "Google OAuth 未启用(GOOGLE_CLIENT_ID 未配置)",
        "en": "Google OAuth is not enabled (GOOGLE_CLIENT_ID not configured)",
    },
    "auth.google_email_unverified": {
        "zh": "Google 账号邮箱未验证",
        "en": "Your Google account email is not verified",
    },
    "auth.verify_token_invalid": {
        "zh": "验证链接无效或已过期",
        "en": "Verification link is invalid or has expired",
    },
    "auth.user_not_found": {
        "zh": "用户不存在",
        "en": "User not found",
    },
    "auth.oauth_only_no_password_change": {
        "zh": "你通过 Google 登录,账户安全由 Google 管理,无需在此修改密码",
        "en": (
            "You signed in with Google; account security is managed by Google, "
            "so there is no password to change here"
        ),
    },
    "auth.old_password_incorrect": {
        "zh": "旧密码错误",
        "en": "Current password is incorrect",
    },
    # 工单
    "support.unknown_category": {"zh": "未知工单类型", "en": "Unknown ticket category"},
    "support.description_empty": {"zh": "问题描述不能为空", "en": "Description cannot be empty"},
    "support.description_too_long": {
        "zh": "问题描述过长(上限 {max_chars} 字)",
        "en": "Description too long (max {max_chars} characters)",
    },
    "support.contact_email_invalid": {
        "zh": "联系邮箱格式不正确",
        "en": "Contact email format is invalid",
    },
    "support.too_many_images": {
        "zh": "最多上传 {max_images} 张图片",
        "en": "You can upload at most {max_images} images",
    },
    "support.image_type_unsupported": {
        "zh": "图片仅支持 JPEG / PNG",
        "en": "Only JPEG / PNG images are supported",
    },
    "support.image_too_large": {
        "zh": "单张图片不得超过 {max_mb} MB",
        "en": "Each image must not exceed {max_mb} MB",
    },
    # 虚拟交易
    "virtual.account_not_activated": {
        "zh": "该市场资金未激活",
        "en": "This market's account is not activated",
    },
    "virtual.hk_symbol_not_in_pool": {
        "zh": "该标的不在港股可下单池",
        "en": "This symbol is not in the HK tradable pool",
    },
    "virtual.hk_min_one_lot": {
        "zh": "港股按手交易 · 每手 {lot} 股 · 最少下单 1 手({lot} 股)",
        "en": (
            "HK trades in board lots · {lot} shares per lot"
            " · minimum order is 1 lot ({lot} shares)"
        ),
    },
    "virtual.market_direction_unsupported": {
        "zh": "市场 {market} 不支持方向 {direction}",
        "en": "Market {market} does not support direction {direction}",
    },
    "virtual.spot_plan_buy_only": {
        "zh": "现货仅支持按计划价限价买入(看空请走平仓,不经此端点)",
        "en": (
            "Spot only supports limit-buy at the planned price "
            "(to go short, close a position instead — not via this endpoint)"
        ),
    },
    "virtual.qty_below_min_unit": {
        "zh": "按预设名义与入场价算出的数量不足一个最小交易单位",
        "en": (
            "The quantity derived from the preset notional and entry price "
            "is below one minimum trading unit"
        ),
    },
    "virtual.perp_limit_requires_margin_fields": {
        "zh": "perp 限价单须填写杠杆 / 保证金 / 仓位模式",
        "en": "Perp limit orders require leverage / margin / margin mode",
    },
    "virtual.perp_limit_open_side_mismatch": {
        "zh": "perp 限价开仓:{position_side} 仓须用 {side} 方向",
        "en": "Perp limit open: a {position_side} position must use the {side} side",
    },
    "virtual.limit_requires_quantity": {
        "zh": "限价单必须填写数量",
        "en": "Limit orders require a quantity",
    },
    "virtual.spot_limit_rejects_margin_fields": {
        "zh": "现货限价单不接受杠杆 / 保证金 / 仓位模式",
        "en": "Spot limit orders do not accept leverage / margin / margin mode",
    },
    "virtual.sltp_rejects_margin_fields": {
        "zh": "止损/止盈单不接受杠杆 / 保证金 / 仓位模式",
        "en": "Stop-loss / take-profit orders do not accept leverage / margin / margin mode",
    },
    "virtual.sltp_closing_side_mismatch": {
        "zh": "止损/止盈是平仓单:{position_side} 仓须用 {side}",
        "en": (
            "Stop-loss / take-profit are closing orders: "
            "a {position_side} position must use {side}"
        ),
    },
    "virtual.market_account_not_set": {
        "zh": "该市场资金未设置 · 请先去个人设置页填写",
        "en": (
            "This market's account is not set up"
            " · please configure it on your settings page first"
        ),
    },
    "virtual.no_active_position_for_sltp": {
        "zh": "无对应活仓 · 止损/止盈需先持有该方向仓位",
        "en": (
            "No matching open position · stop-loss / take-profit "
            "requires holding a position in that direction first"
        ),
    },
    "virtual.conditional_order_not_found_or_uncancelable": {
        "zh": "条件单不存在或不可撤销",
        "en": "Conditional order not found or cannot be cancelled",
    },
    # 决策卡 / 策略 · purpose 子 key 解双层插值
    "analysis.purpose_gen_signals": {"zh": "生成策略信号", "en": "generate strategy signals"},
    "analysis.purpose_recommend": {"zh": "推荐策略", "en": "recommend a strategy"},
    "analysis.perp_kline_insufficient_chan": {
        "zh": "perp K 线数据不足 30 根 · 无法做缠论分析:{e}",
        "en": (
            "Perp K-line data insufficient (fewer than 30 bars) · "
            "unable to run Chan Theory analysis: {e}"
        ),
    },
    "analysis.kline_insufficient_chan": {
        "zh": "K 线数据不足 30 根 · 无法做缠论分析:{e}",
        "en": (
            "K-line data insufficient (fewer than 30 bars) · "
            "unable to run Chan Theory analysis: {e}"
        ),
    },
    "analysis.perp_kline_insufficient_decision_card": {
        "zh": "perp K 线数据不足 30 根 · 无法生成决策卡:{e}",
        "en": (
            "Perp K-line data insufficient (fewer than 30 bars) · "
            "unable to generate decision card: {e}"
        ),
    },
    "analysis.kline_insufficient_decision_card": {
        "zh": "K 线数据不足 30 根 · 无法生成决策卡:{e}",
        "en": (
            "K-line data insufficient (fewer than 30 bars) · "
            "unable to generate decision card: {e}"
        ),
    },
    "analysis.perp_kline_insufficient_purpose": {
        "zh": "perp K 线数据不足 · 无法{purpose}:{e}",
        "en": "Perp K-line data insufficient · unable to {purpose}: {e}",
    },
    "analysis.kline_insufficient_purpose": {
        "zh": "K 线数据不足 · 无法{purpose}:{e}",
        "en": "K-line data insufficient · unable to {purpose}: {e}",
    },
    # 告警规则
    "alert_rule.unknown_indicator": {
        "zh": "未知指标:{indicator}",
        "en": "Unknown indicator: {indicator}",
    },
    "alert_rule.indicator_market_unsupported": {
        "zh": "指标 {indicator} 不支持市场 {market}",
        "en": "Indicator {indicator} does not support market {market}",
    },
    "alert_rule.indicator_requires_symbol": {
        "zh": "指标 {indicator} 需要 symbol",
        "en": "Indicator {indicator} requires a symbol",
    },
    "alert_rule.max_rules_reached": {
        "zh": "告警规则数已达上限({max_rules})· 请先删除部分规则",
        "en": "Alert rule limit reached ({max_rules}) · please delete some rules first",
    },
    "alert_rule.not_found_or_forbidden": {
        "zh": "规则不存在或无权限",
        "en": "Rule not found or access denied",
    },
    # 自选
    "watchlist.already_added": {
        "zh": "该标的已在自选列表",
        "en": "This symbol is already in your watchlist",
    },
    "watchlist.crypto_symbol_not_found": {
        "zh": "加密交易对不存在:{symbol}(请用 Binance 现货交易对,如 BTC/USDT)",
        "en": (
            "Crypto trading pair not found: {symbol}"
            " (use a Binance spot pair, e.g. BTC/USDT)"
        ),
    },
    "watchlist.item_not_found": {
        "zh": "自选股不存在或无权限",
        "en": "Watchlist item not found or access denied",
    },
    "watchlist.item_not_found_by_id": {
        "zh": "自选股 {item_id} 不存在或无权限",
        "en": "Watchlist item {item_id} not found or access denied",
    },
    # 通知
    "notifications.dott_requires_pro": {
        "zh": "做T信号 TG 通知为 Pro 会员专属 · 请先开通 Pro",
        "en": "Day-trade signal Telegram alerts are Pro-only · please upgrade to Pro",
    },
    "notifications.telegram_not_bound": {
        "zh": "未绑定 Telegram · 请先在 bot 里 /start 绑定",
        "en": "Telegram not bound · please bind via /start in the bot first",
    },
    # 支付
    "payment.gateway_unavailable": {
        "zh": "支付网关暂不可用,请稍后重试",
        "en": "Payment gateway is temporarily unavailable, please try again later",
    },
    "payment.order_not_found": {"zh": "订单不存在", "en": "Order not found"},
    # 训练营
    "academy.unknown_article_slug": {
        "zh": "未知文章 slug: {slug}",
        "en": "Unknown article slug: {slug}",
    },
    "academy.unknown_exam_stage": {
        "zh": "未知模块或暂无结业测验: {stage}",
        "en": "Unknown module or no exam available yet: {stage}",
    },
    # 加密合约
    "crypto.too_many_symbols": {
        "zh": "symbols 最多 200 个 · 当前 {count}",
        "en": "At most 200 symbols allowed · currently {count}",
    },
    "crypto.no_oi_data": {
        "zh": "symbol {symbol} 没有 OI 数据 · 数据预热未覆盖此 symbol",
        "en": "No OI data for symbol {symbol} · data warm-up has not covered this symbol",
    },
    "crypto.no_premium_funding_data": {
        "zh": "symbol {symbol} 没有 premium / funding 数据 · 数据预热未覆盖此 symbol",
        "en": (
            "No premium / funding data for symbol {symbol}"
            " · data warm-up has not covered this symbol"
        ),
    },
    # K 线图
    "chart.insufficient_kline_data": {
        "zh": "K线数据不足(回源后仍 {count} 根)· 无法渲染",
        "en": "Insufficient K-line data (still {count} bars after refetch) · cannot render",
    },
    # 结构诊断
    "structure.no_factor_data": {
        "zh": "未找到 {symbol} 的合约因子数据,请确认是 USDT 永续合约",
        "en": (
            "No contract factor data found for {symbol},"
            " please confirm it is a USDT perpetual contract"
        ),
    },
    "structure.diagnosis_generation_failed": {
        "zh": "结构诊断生成失败,请稍后重试({e})",
        "en": "Structure diagnosis generation failed, please retry later ({e})",
    },

    # ── 刀3 · 规则层 user-facing 展示文案(feeds_shadow_push=false · zh 逐字节)────────
    # ★排除:boll_state/boll_digest 全部(喂 M1 影子 validate_shadow_push 门禁·红线不碰)·
    #   composite_label(刀2 决策A 归前端)· plan_note LLM prompt 标签(75 prompt 红线)·
    #   strategy_signals scan reasons(拆 刀3b · 6 扫描器穿参侵入性高·见 PR 说明)。
    # 策略推荐 reason(strategy_recommend._pick / recommend_strategy · 术语:趋势/震荡/均值回归)
    "recommend.trend_up": {
        "zh": "近 5 日上行趋势 · 适合均线金叉跟踪趋势",
        "en": "Uptrend over the last 5 days · a moving-average golden cross suits trend-following",
    },
    "recommend.trend_down": {
        "zh": "近 5 日下行趋势 · 适合均线死叉跟踪趋势",
        "en": "Downtrend over the last 5 days · a moving-average death cross suits trend-following",
    },
    "recommend.range_oversold": {
        "zh": "震荡市 + RSI {rsi:.0f} 偏超卖 · 适合 RSI 超卖反弹策略",
        "en": "Range-bound + RSI {rsi:.0f} leaning oversold · an RSI oversold-bounce strategy fits",
    },
    "recommend.range_overbought": {
        "zh": "震荡市 + RSI {rsi:.0f} 偏超买 · 适合 RSI 超买回落策略",
        "en": (
            "Range-bound + RSI {rsi:.0f} leaning overbought"
            " · an RSI overbought-pullback strategy fits"
        ),
    },
    "recommend.range_lower_band": {
        "zh": "震荡市 + 价格贴近布林下轨 · 适合均值回归(博反弹)",
        "en": (
            "Range-bound + price hugging the lower Bollinger band"
            " · mean-reversion (fade for a bounce) fits"
        ),
    },
    "recommend.range_upper_band": {
        "zh": "震荡市 + 价格贴近布林上轨 · 适合均值回归(博回落)",
        "en": (
            "Range-bound + price hugging the upper Bollinger band"
            " · mean-reversion (fade for a pullback) fits"
        ),
    },
    "recommend.range_default": {
        "zh": "震荡市无明显极值 · 默认均线金叉观察趋势启动",
        "en": (
            "Range-bound with no clear extreme · defaulting to the"
            " moving-average cross to watch for a trend start"
        ),
    },
    "recommend.insufficient_data": {
        "zh": "K 线数据不足 · 默认均线金叉策略",
        "en": "Insufficient K-line data · defaulting to the moving-average cross strategy",
    },
    # 告警指标 label(alerts registry IndicatorDef.label · list_indicators 端点展示)
    "alert_indicator.price": {"zh": "最新价", "en": "Latest price"},
    "alert_indicator.price_change_pct": {"zh": "涨跌幅 %", "en": "Change %"},
    "alert_indicator.volume": {"zh": "成交量", "en": "Volume"},
    "alert_indicator.ma_5": {"zh": "MA5", "en": "MA5"},
    "alert_indicator.ma_20": {"zh": "MA20", "en": "MA20"},
    "alert_indicator.ma_60": {"zh": "MA60", "en": "MA60"},
    "alert_indicator.macd_hist": {"zh": "MACD 柱", "en": "MACD histogram"},
    "alert_indicator.rsi_14": {"zh": "RSI(14)", "en": "RSI(14)"},
    "alert_indicator.boll_pctb": {"zh": "布林 %B", "en": "Bollinger %B"},
    "alert_indicator.chan_buy": {"zh": "缠论买点出现", "en": "Chan Theory buy point appears"},
    "alert_indicator.chan_sell": {"zh": "缠论卖点出现", "en": "Chan Theory sell point appears"},
    "alert_indicator.funding_rate": {"zh": "资金费率", "en": "Funding rate"},
    "alert_indicator.open_interest_usd": {"zh": "未平仓额(USD)", "en": "Open interest (USD)"},
    "alert_indicator.long_short_ratio": {
        "zh": "多空比(大户账户)",
        "en": "Long/short ratio (top accounts)",
    },
    "alert_indicator.basis_pct": {"zh": "基差 %", "en": "Basis %"},
    "alert_indicator.fear_greed": {"zh": "恐贪指数", "en": "Fear & Greed index"},
    "alert_indicator.btc_dominance": {"zh": "BTC 占比 %", "en": "BTC dominance %"},
    "alert_indicator.cn_breadth_up_ratio": {
        "zh": "A股上涨家数占比 %",
        "en": "CN advancers ratio %",
    },
    "alert_indicator.hk_breadth_up_ratio": {
        "zh": "港股上涨家数占比 %",
        "en": "HK advancers ratio %",
    },
    "alert_indicator.sector_change_pct": {
        "zh": "板块涨跌 %(symbol=板块名)",
        "en": "Sector change % (symbol = sector name)",
    },
    "alert_indicator.index_change_pct": {
        "zh": "指数涨跌 %(symbol=指数代码)",
        "en": "Index change % (symbol = index code)",
    },
}


def translate(key: str, lang: str = "zh", /, **params: object) -> str:
    """按 key + 语言取本地化文案 · 缺 key 返 key 兜底(不抛)· 有 params 走 str.format 插值。

    ★zh 恒等契约:zh 值 = 今天线上中文字面量逐字节复刻 · lang="zh" 逐字节等于改造前。
    ★未登记 key → warning + 返回 key(不 KeyError 拖垮请求 · 便于灰度补表)。
    """
    entry = _CATALOG.get(key)
    if entry is None:
        logger.warning("[i18n] 未登记文案 key=%r · 返回 key 兜底", key)
        return key
    template = entry.get(lang) or entry["zh"]
    return template.format(**params) if params else template
