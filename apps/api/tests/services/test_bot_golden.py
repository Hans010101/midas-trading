"""TG bot 输出零回归 golden 测试 · ADR 0032 阶段一命门。

GOLDEN = 重构前 telegram_ui.render_* 的【字节级标准答案】(由 _dump_golden 一次性冻结)。
本测试断言新链路 render_for_telegram(build_X(...)) 与 GOLDEN 逐字节(text)+ 结构(keyboard)
一致 —— 即 TG bot 行为对用户零可见变化。任一不一致 = 回归,CI 红。

覆盖全部 render_*(主菜单 / 绑定提示 / 行情 / K线 / 自选 / 持仓 / 下单全流程含二次确认卡
+ 成交回执 / 告警规则 / 安静时段 / 限流 / 错误态)· 多变体(空/非空 · 各市场 · 有无价)。
"""
from __future__ import annotations

import pytest

from app.services.bot import replies
from app.services.bot.order import OrderPreview
from app.services.bot.query import (
    AlertRuleRow,
    PositionRow,
    SymbolQuote,
    WatchlistRow,
)
from app.services.bot.quiet import QuietHoursView
from app.services.bot.renderers.telegram import render_for_telegram

GOLDEN: dict[str, dict[str, object]] = {'main_menu': {'text': '*点金 Midas · 迷你终端*\n\n点下方按钮选择功能 ↓\n\n也可直接发送 `/price <代码>` 查行情',
               'keyboard': {'inline_keyboard': [[{'text': '📊 行情查询', 'callback_data': 'menu:quote'},
                                                 {'text': '📈 K线图', 'callback_data': 'menu:kline'}],
                                                [{'text': '⭐ 我的自选',
                                                  'callback_data': 'act:watchlist'},
                                                 {'text': '💼 我的持仓',
                                                  'callback_data': 'act:positions'}],
                                                [{'text': '🛒 下单', 'callback_data': 'menu:order'},
                                                 {'text': '🔔 告警规则', 'callback_data': 'menu:rules'}],
                                                [{'text': '🌙 安静时段',
                                                  'callback_data': 'menu:quiet'}]]}},
 'market_picker_quote': {'text': '*点金 Midas*\n\n查行情 —— 先选市场:',
                         'keyboard': {'inline_keyboard': [[{'text': 'A股',
                                                            'callback_data': 'ask:quote:cn'},
                                                           {'text': '美股',
                                                            'callback_data': 'ask:quote:us'},
                                                           {'text': '加密',
                                                            'callback_data': 'ask:quote:crypto'}],
                                                          [{'text': '⬅️ 返回菜单',
                                                            'callback_data': 'menu:main'}]]}},
 'market_picker_kline': {'text': '*点金 Midas*\n\n看K线 —— 先选市场:',
                         'keyboard': {'inline_keyboard': [[{'text': 'A股',
                                                            'callback_data': 'ask:kline:cn'},
                                                           {'text': '美股',
                                                            'callback_data': 'ask:kline:us'},
                                                           {'text': '加密',
                                                            'callback_data': 'ask:kline:crypto'}],
                                                          [{'text': '⬅️ 返回菜单',
                                                            'callback_data': 'menu:main'}]]}},
 'ask_symbol_quote_cn': {'text': '*点金 Midas*\n\nA股 · 查行情\n请发送代码,例如 `600519`',
                         'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                            'callback_data': 'menu:main'}]]}},
 'ask_symbol_kline_crypto': {'text': '*点金 Midas*\n\n加密 · 看K线\n请发送代码,例如 `BTC/USDT`',
                             'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                                'callback_data': 'menu:main'}]]}},
 'quote_full': {'text': '*点金 Midas · 行情*\n'
                        '\n'
                        '📊 BTC/USDT · 加密\n'
                        '最新价 63,200 USDT\n'
                        '涨跌幅 🔴 +2.34%\n'
                        '成交量 12,345.678\n'
                        '资金费率 +0.0100%\n'
                        '未平仓额 $1.23B\n'
                        '多空比(大户) 1.85\n'
                        '基差 +0.123%',
                'keyboard': {'inline_keyboard': [[{'text': '📈 网页看K线',
                                                   'url': 'http://localhost:3000/crypto-preview?symbol=BTCUSDT'}],
                                                 [{'text': '⬅️ 返回菜单',
                                                   'callback_data': 'menu:main'}]]}},
 'quote_min': {'text': '*点金 Midas · 行情*\n\n📊 600519 · A股\n最新价 ¥1,688\n涨跌幅 🟢 -1.20%\n成交量 98,765',
               'keyboard': {'inline_keyboard': [[{'text': '📈 网页看K线',
                                                  'url': 'http://localhost:3000/cn-preview?symbol=600519'}],
                                                [{'text': '⬅️ 返回菜单',
                                                  'callback_data': 'menu:main'}]]}},
 'quote_noprice': {'text': '*点金 Midas · 行情*\n\n📊 NVDA · 美股\n涨跌幅 —',
                   'keyboard': {'inline_keyboard': [[{'text': '📈 网页看K线',
                                                      'url': 'http://localhost:3000/us-preview?symbol=NVDA'}],
                                                    [{'text': '⬅️ 返回菜单',
                                                      'callback_data': 'menu:main'}]]}},
 'symbol_not_found': {'text': '*点金 Midas*\n\n未找到 600519(A股)的数据。\n请确认代码,或换一个再试(只查已采集标的)。',
                      'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                         'callback_data': 'menu:main'}]]}},
 'kline_link': {'text': '*点金 Midas · K线*\n\n📈 NVDA · 美股\n点下方按钮在网页打开完整 K 线图(含缠论 / 指标)。',
                'keyboard': {'inline_keyboard': [[{'text': '📈 网页看K线',
                                                   'url': 'http://localhost:3000/us-preview?symbol=NVDA'}],
                                                 [{'text': '⬅️ 返回菜单',
                                                   'callback_data': 'menu:main'}]]}},
 'watchlist_empty': {'text': '*点金 Midas · 自选*\n\n你还没有自选标的。\n在网页端工作台用 Cmd/Ctrl+K 添加。',
                     'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                        'callback_data': 'menu:main'}]]}},
 'watchlist_rows': {'text': '*点金 Midas · 自选*\n\nNVDA · 美股  $145.0  🔴 +1.20%\nMU/USDT · 加密  —  —',
                    'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                       'callback_data': 'menu:main'}]]}},
 'positions_empty': {'text': '*点金 Midas · 持仓*\n\n当前没有活仓。\n所有交易均为 VIRTUAL · 模拟。',
                     'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                        'callback_data': 'menu:main'}]]}},
 'positions_rows': {'text': '*点金 Midas · 持仓* (VIRTUAL · 模拟)\n'
                            '\n'
                            'NVDA · 美股 · 多  10 @ $140.0\n'
                            'BTC/USDT · 永续20x · 空  0.5 @ 63,000 USDT',
                    'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                       'callback_data': 'menu:main'}]]}},
 'order_market_picker': {'text': '*点金 Midas · 下单* (VIRTUAL · 模拟)\n\n🛒 全程虚拟资金 · 先选市场:',
                         'keyboard': {'inline_keyboard': [[{'text': 'A股',
                                                            'callback_data': 'omkt:cn'},
                                                           {'text': '美股',
                                                            'callback_data': 'omkt:us'},
                                                           {'text': '加密合约',
                                                            'callback_data': 'omkt:crypto'}],
                                                          [{'text': '⬅️ 返回菜单',
                                                            'callback_data': 'menu:main'}]]}},
 'order_ask_symbol_crypto': {'text': '*点金 Midas · 下单* (加密为永续合约 · 逐仓)\n'
                                     '\n'
                                     '加密 · 请发送要下单的代码,例如 `BTC/USDT`',
                             'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                                'callback_data': 'menu:main'}]]}},
 'order_ask_symbol_cn': {'text': '*点金 Midas · 下单* \n\nA股 · 请发送要下单的代码,例如 `600519`',
                         'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                            'callback_data': 'menu:main'}]]}},
 'order_directions_perp': {'text': '*点金 Midas · 下单* (VIRTUAL · 模拟)\n'
                                   '\n'
                                   'BTC/USDT · 加密\n'
                                   '当前价 63,200 USDT\n'
                                   '\n'
                                   '选择操作:',
                           'keyboard': {'inline_keyboard': [[{'text': '开多',
                                                              'callback_data': 'odir:open_long'},
                                                             {'text': '开空',
                                                              'callback_data': 'odir:open_short'}],
                                                            [{'text': '平仓',
                                                              'callback_data': 'odir:close'}],
                                                            [{'text': '⬅️ 返回菜单',
                                                              'callback_data': 'menu:main'}]]}},
 'order_directions_noprice': {'text': '*点金 Midas · 下单* (VIRTUAL · 模拟)\n\nNVDA · 美股\n—\n\n选择操作:',
                              'keyboard': {'inline_keyboard': [[{'text': '买入',
                                                                 'callback_data': 'odir:buy'},
                                                                {'text': '卖出',
                                                                 'callback_data': 'odir:sell'}],
                                                               [{'text': '卖空',
                                                                 'callback_data': 'odir:short'},
                                                                {'text': '平空',
                                                                 'callback_data': 'odir:cover'}],
                                                               [{'text': '⬅️ 返回菜单',
                                                                 'callback_data': 'menu:main'}]]}},
 'order_preview_perp': {'text': '*点金 Midas · 下单确认* (VIRTUAL · 模拟)\n'
                                '\n'
                                '开多 · BTC/USDT · 加密\n'
                                '预估价 63,200 USDT\n'
                                '数量 ~0.5\n'
                                '名义 ~31,600 USDT\n'
                                '杠杆 20x · 逐仓\n'
                                '\n'
                                '⚠️ 确认后立即以【虚拟资金】下单,不可撤销。\n'
                                '\n'
                                '_本次为模拟交易,不构成投资建议_',
                        'keyboard': {'inline_keyboard': [[{'text': '✅ 确认下单',
                                                           'callback_data': 'ordok'},
                                                          {'text': '✖️ 取消',
                                                           'callback_data': 'ordno'}]]}},
 'order_preview_spot': {'text': '*点金 Midas · 下单确认* (VIRTUAL · 模拟)\n'
                                '\n'
                                '买入 · NVDA · 美股\n'
                                '预估价 $145.0\n'
                                '数量 ~10\n'
                                '名义 ~$1,450\n'
                                '\n'
                                '⚠️ 确认后立即以【虚拟资金】下单,不可撤销。\n'
                                '\n'
                                '_本次为模拟交易,不构成投资建议_',
                        'keyboard': {'inline_keyboard': [[{'text': '✅ 确认下单',
                                                           'callback_data': 'ordok'},
                                                          {'text': '✖️ 取消',
                                                           'callback_data': 'ordno'}]]}},
 'order_unavailable': {'text': '*点金 Midas · 下单*\n\n无法下单:可能暂无最新报价,或(平仓时)当前没有可平持仓。\n请确认代码 / 持仓后再试。',
                       'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                          'callback_data': 'menu:main'}]]}},
 'order_result': {'text': '*点金 Midas · 已拒绝*\n\n余额不足,无法下单。\n\n_本次为模拟交易,不构成投资建议_',
                  'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                     'callback_data': 'menu:main'}]]}},
 'order_receipt': {'text': '✅ *点金 Midas · 合约成交*\n'
                           '\n'
                           '📊 BTC/USDT · 永续 · 逐仓 20x\n'
                           '开多 0.5 · 成交价 63,200 USDT\n'
                           '\n'
                           '_本次为模拟交易,不构成投资建议_',
                   'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                      'callback_data': 'menu:main'}]]}},
 'order_symbol_invalid': {'text': '*点金 Midas · 下单*\n'
                                  '\n'
                                  '未找到「xyz」对应的标的,请重新输入。\n'
                                  '例:BTC / BTCUSDT / BTC/USDT',
                          'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                             'callback_data': 'menu:main'}]]}},
 'order_direction_hint': {'text': '*点金 Midas · 下单*\n'
                                  '\n'
                                  '请点上方按钮选择方向(开多 / 开空 / 平仓)。\n'
                                  '如需更换标的,请点「🛒 下单」重新开始。',
                          'keyboard': {'inline_keyboard': [[{'text': '⬅️ 返回菜单',
                                                             'callback_data': 'menu:main'}]]}},
 'order_cancelled': {'text': '*点金 Midas · 下单*\n\n已取消,未下单。',
                     'keyboard': {'inline_keyboard': [[{'text': '📊 行情查询',
                                                        'callback_data': 'menu:quote'},
                                                       {'text': '📈 K线图',
                                                        'callback_data': 'menu:kline'}],
                                                      [{'text': '⭐ 我的自选',
                                                        'callback_data': 'act:watchlist'},
                                                       {'text': '💼 我的持仓',
                                                        'callback_data': 'act:positions'}],
                                                      [{'text': '🛒 下单',
                                                        'callback_data': 'menu:order'},
                                                       {'text': '🔔 告警规则',
                                                        'callback_data': 'menu:rules'}],
                                                      [{'text': '🌙 安静时段',
                                                        'callback_data': 'menu:quiet'}]]}},
 'rate_limited': {'text': '*点金 Midas*\n\n操作过于频繁,请稍后再试(防滥用限流)。', 'keyboard': None},
 'alert_rules_empty': {'text': '*点金 Midas · 告警规则*\n'
                               '\n'
                               '你还没有告警规则。\n'
                               '点「✨ 一键应用推荐规则」快速开始,或在网页端【设置 → 告警规则】自定义。',
                       'keyboard': {'inline_keyboard': [[{'text': '✨ 一键应用推荐规则',
                                                          'callback_data': 'rules:apply'}],
                                                        [{'text': '⬅️ 返回菜单',
                                                          'callback_data': 'menu:main'}]]}},
 'alert_rules_rows': {'text': '*点金 Midas · 告警规则*\n\n🔔=启用 / 🔕=停用 · 点规则可切换状态;全量新建在网页端。',
                      'keyboard': {'inline_keyboard': [[{'text': '🔔 价格>70,000 · BTC/USDT',
                                                         'callback_data': 'rules:toggle:1'}],
                                                       [{'text': '🔕 涨跌幅≤-5% · 美股',
                                                         'callback_data': 'rules:toggle:2'}],
                                                       [{'text': '✨ 一键应用推荐规则',
                                                         'callback_data': 'rules:apply'}],
                                                       [{'text': '⬅️ 返回菜单',
                                                         'callback_data': 'menu:main'}]]}},
 'alert_rules_note': {'text': '*点金 Midas · 告警规则*\n'
                              '\n'
                              '已应用推荐:新增 2 条 · 跳过 1 条\n'
                              '\n'
                              '🔔=启用 / 🔕=停用 · 点规则可切换状态;全量新建在网页端。',
                      'keyboard': {'inline_keyboard': [[{'text': '🔔 价格>70,000 · BTC/USDT',
                                                         'callback_data': 'rules:toggle:1'}],
                                                       [{'text': '✨ 一键应用推荐规则',
                                                         'callback_data': 'rules:apply'}],
                                                       [{'text': '⬅️ 返回菜单',
                                                         'callback_data': 'menu:main'}]]}},
 'quiet_hours_on': {'text': '*点金 Midas · 安静时段*\n'
                            '\n'
                            '🌙 状态:已启用\n'
                            '⏰ 时段:23:00 – 次日 07:00\n'
                            '🌐 时区:Asia/Shanghai\n'
                            '\n'
                            '⚠️ 安静时段内仅静默【普通告警】(自选异动 / 规则告警),\n'
                            '    *成交 / 强平等关键事件照常推送*,夜间不漏。\n'
                            '\n'
                            '按下方按钮调整开关 / 起止小时;时区切换请到网页端。',
                    'keyboard': {'inline_keyboard': [[{'text': '🔕 关闭安静时段',
                                                       'callback_data': 'quiet:toggle'}],
                                                     [{'text': '−1h', 'callback_data': 'quiet:s-'},
                                                      {'text': '起 23:00',
                                                       'callback_data': 'quiet:noop'},
                                                      {'text': '+1h', 'callback_data': 'quiet:s+'}],
                                                     [{'text': '−1h', 'callback_data': 'quiet:e-'},
                                                      {'text': '止 07:00',
                                                       'callback_data': 'quiet:noop'},
                                                      {'text': '+1h', 'callback_data': 'quiet:e+'}],
                                                     [{'text': '🌐 时区调整 · 在网页端',
                                                       'url': 'http://localhost:3000/settings'}],
                                                     [{'text': '⬅️ 返回菜单',
                                                       'callback_data': 'menu:main'}]]}},
 'quiet_hours_off': {'text': '*点金 Midas · 安静时段*\n'
                             '\n'
                             '☀️ 状态:已关闭\n'
                             '⏰ 时段:08:00 – 22:00\n'
                             '🌐 时区:America/New_York\n'
                             '\n'
                             '⚠️ 安静时段内仅静默【普通告警】(自选异动 / 规则告警),\n'
                             '    *成交 / 强平等关键事件照常推送*,夜间不漏。\n'
                             '\n'
                             '按下方按钮调整开关 / 起止小时;时区切换请到网页端。',
                     'keyboard': {'inline_keyboard': [[{'text': '🔔 启用安静时段',
                                                        'callback_data': 'quiet:toggle'}],
                                                      [{'text': '−1h', 'callback_data': 'quiet:s-'},
                                                       {'text': '起 08:00',
                                                        'callback_data': 'quiet:noop'},
                                                       {'text': '+1h',
                                                        'callback_data': 'quiet:s+'}],
                                                      [{'text': '−1h', 'callback_data': 'quiet:e-'},
                                                       {'text': '止 22:00',
                                                        'callback_data': 'quiet:noop'},
                                                       {'text': '+1h',
                                                        'callback_data': 'quiet:e+'}],
                                                      [{'text': '🌐 时区调整 · 在网页端',
                                                        'url': 'http://localhost:3000/settings'}],
                                                      [{'text': '⬅️ 返回菜单',
                                                        'callback_data': 'menu:main'}]]}},
 'not_bound': {'text': '*点金 Midas*\n'
                       '\n'
                       '你的 Telegram 还没绑定 Midas 账号。\n'
                       '请到网页端【设置 → 消息推送】点「绑定 Telegram」,按提示完成绑定后再用。',
               'keyboard': None},
 'hint': {'text': '*点金 Midas*\n\n发送 /menu 打开功能菜单,或 `/price <代码>` 直接查行情。',
          'keyboard': {'inline_keyboard': [[{'text': '📊 行情查询', 'callback_data': 'menu:quote'},
                                            {'text': '📈 K线图', 'callback_data': 'menu:kline'}],
                                           [{'text': '⭐ 我的自选', 'callback_data': 'act:watchlist'},
                                            {'text': '💼 我的持仓', 'callback_data': 'act:positions'}],
                                           [{'text': '🛒 下单', 'callback_data': 'menu:order'},
                                            {'text': '🔔 告警规则', 'callback_data': 'menu:rules'}],
                                           [{'text': '🌙 安静时段', 'callback_data': 'menu:quiet'}]]}}}

# ── fixtures(与 _dump_golden 一致 · 决定 GOLDEN 的输入)────────────────
_Q_FULL = SymbolQuote(
    market="crypto", symbol="BTC/USDT", currency="USDT", price=63200.5,
    change_pct=2.34, volume=12345.678, funding_rate=0.0001,
    open_interest_usd=1.23e9, long_short_ratio=1.85, basis_pct=0.123,
)
_Q_MIN = SymbolQuote(
    market="cn", symbol="600519", currency="CNY", price=1688.0,
    change_pct=-1.2, volume=98765.0,
)
_Q_NOPRICE = SymbolQuote(
    market="us", symbol="NVDA", currency="USD", price=None,
    change_pct=None, volume=None,
)
_WL = [
    WatchlistRow(market="us", symbol="NVDA", price=145.0, change_pct=1.2),
    WatchlistRow(market="crypto", symbol="MU/USDT", price=None, change_pct=None),
]
_POS = [
    PositionRow(market="us", symbol="NVDA", kind="spot", side="long",
                quantity=10.0, avg_entry_price=140.0, currency="USD"),
    PositionRow(market="crypto", symbol="BTC/USDT", kind="perp", side="short",
                quantity=0.5, avg_entry_price=63000.0, currency="USDT", leverage=20),
]
_PREVIEW_PERP = OrderPreview(
    market="crypto", symbol="BTC/USDT", direction="open_long",
    direction_label="开多", is_open=True, est_price=63200.0, quantity=0.5,
    notional=31600.0, currency="USDT", leverage=20,
)
_PREVIEW_SPOT = OrderPreview(
    market="us", symbol="NVDA", direction="buy", direction_label="买入",
    is_open=True, est_price=145.0, quantity=10.0, notional=1450.0,
    currency="USD", leverage=None,
)
_RULES = [
    AlertRuleRow(rule_id=1, market="crypto", symbol="BTC/USDT",
                 indicator_label="价格", operator="gt", threshold=70000.0,
                 unit=None, enabled=True),
    AlertRuleRow(rule_id=2, market="us", symbol=None, indicator_label="涨跌幅",
                 operator="lte", threshold=-5.0, unit="%", enabled=False),
]
_QV_ON = QuietHoursView(enabled=True, start_hour=23, end_hour=7, tz="Asia/Shanghai")
_QV_OFF = QuietHoursView(enabled=False, start_hour=8, end_hour=22, tz="America/New_York")
_RECEIPT_BODY = (
    "*点金 Midas · 合约成交*\n\n"
    "📊 BTC/USDT · 永续 · 逐仓 20x\n开多 0.5 · 成交价 63,200 USDT\n\n"
    "_本次为模拟交易,不构成投资建议_"
)

# key → 新链路 ReplyModel(交给 render_for_telegram 后比对 GOLDEN[key])
CASES = {
    "main_menu": replies.build_main_menu(),
    "market_picker_quote": replies.build_market_picker("quote"),
    "market_picker_kline": replies.build_market_picker("kline"),
    "ask_symbol_quote_cn": replies.build_ask_symbol("quote", "cn"),
    "ask_symbol_kline_crypto": replies.build_ask_symbol("kline", "crypto"),
    "quote_full": replies.build_quote(_Q_FULL),
    "quote_min": replies.build_quote(_Q_MIN),
    "quote_noprice": replies.build_quote(_Q_NOPRICE),
    "symbol_not_found": replies.build_symbol_not_found("cn", "600519"),
    "kline_link": replies.build_kline_link("us", "NVDA"),
    "watchlist_empty": replies.build_watchlist([]),
    "watchlist_rows": replies.build_watchlist(_WL),
    "positions_empty": replies.build_positions([]),
    "positions_rows": replies.build_positions(_POS),
    "order_market_picker": replies.build_order_market_picker(),
    "order_ask_symbol_crypto": replies.build_order_ask_symbol("crypto"),
    "order_ask_symbol_cn": replies.build_order_ask_symbol("cn"),
    "order_directions_perp": replies.build_order_directions("crypto", "BTC/USDT", 63200.0),
    "order_directions_noprice": replies.build_order_directions("us", "NVDA", None),
    "order_preview_perp": replies.build_order_preview(_PREVIEW_PERP),
    "order_preview_spot": replies.build_order_preview(_PREVIEW_SPOT),
    "order_unavailable": replies.build_order_unavailable(),
    "order_result": replies.build_order_result("已拒绝", "余额不足,无法下单。"),
    "order_receipt": replies.build_order_receipt(_RECEIPT_BODY),
    "order_symbol_invalid": replies.build_order_symbol_invalid("crypto", "xyz"),
    "order_direction_hint": replies.build_order_direction_hint(),
    "order_cancelled": replies.build_order_cancelled(),
    "rate_limited": replies.build_rate_limited(),
    "alert_rules_empty": replies.build_alert_rules([]),
    "alert_rules_rows": replies.build_alert_rules(_RULES),
    "alert_rules_note": replies.build_alert_rules(_RULES[:1], note="已应用推荐:新增 2 条 · 跳过 1 条"),
    "quiet_hours_on": replies.build_quiet_hours(_QV_ON),
    "quiet_hours_off": replies.build_quiet_hours(_QV_OFF),
    "not_bound": replies.build_not_bound(),
    "hint": replies.build_hint(),
}


def test_golden_covers_all_cases() -> None:
    """GOLDEN 与 CASES 键集合必须完全一致(防漏测某个 render)。"""
    assert set(CASES) == set(GOLDEN)


@pytest.mark.parametrize("key", list(GOLDEN))
def test_telegram_render_byte_identical(key: str) -> None:
    """🔴 零回归:新链路渲染必须与冻结的旧 render_* 输出逐字节 + 结构一致。"""
    reply = render_for_telegram(CASES[key])
    assert reply.text == GOLDEN[key]["text"], f"[{key}] text 字节级回归"
    assert reply.keyboard == GOLDEN[key]["keyboard"], f"[{key}] keyboard 结构回归"


# ── 🔴 免责分级守卫(阶段四-A · 独立于 GOLDEN · 防误删交易类免责)──────────
_TRADE_KEYS = {
    "order_preview_perp", "order_preview_spot", "order_result", "order_receipt",
}
_DISPLAY_KEYS = sorted(set(GOLDEN) - _TRADE_KEYS)
_TRADE_DISCLAIMER = "本次为模拟交易,不构成投资建议"


@pytest.mark.parametrize("key", _DISPLAY_KEYS)
def test_display_messages_have_no_disclaimer(key: str) -> None:
    """🔴 展示/导航/配置类:不带任何免责声明(分级:去掉)。"""
    text = render_for_telegram(CASES[key]).text
    assert "仅供参考" not in text, f"[{key}] 展示类不应含免责"
    assert _TRADE_DISCLAIMER not in text, f"[{key}] 展示类不应含交易免责"


@pytest.mark.parametrize("key", sorted(_TRADE_KEYS))
def test_trade_messages_keep_trade_disclaimer(key: str) -> None:
    """🔴 交易类(下单确认/成交/拒单/回执):必带「本次为模拟交易,不构成投资建议」· 不可误删。"""
    text = render_for_telegram(CASES[key]).text
    assert _TRADE_DISCLAIMER in text, f"[{key}] 交易类必须含交易口径免责"
