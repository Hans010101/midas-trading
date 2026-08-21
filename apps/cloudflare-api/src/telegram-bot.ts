import { fetchMarketKlines } from './market'
import { executePerpOrder, executeSpotOrder } from './virtual-trading'

type Market = 'cn' | 'us' | 'hk' | 'crypto'
type SessionState = Readonly<{
  action?: 'quote' | 'kline' | 'order_symbol' | 'order_confirm'
  market?: Market
  symbol?: string
  direction?: string
  preview?: string
}>
type TelegramUpdate = Readonly<{
  message?: { text?: unknown; chat?: { id?: unknown } }
  callback_query?: {
    id?: unknown
    data?: unknown
    message?: { chat?: { id?: unknown } }
  }
}>
type TelegramMarkup = Readonly<Record<string, unknown>>

const COMMAND_LIMIT = 20
const ORDER_LIMIT = 10
const WINDOW_MS = 60_000
const SESSION_TTL_MS = 10 * 60_000
const COMMON_CRYPTO = new Set([
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'TRX', 'AVAX', 'LINK',
  'DOT', 'SUI', 'TON', 'LTC', 'BCH', 'UNI', 'AAVE', 'PEPE', 'SHIB', 'NEAR',
])
const MARKETS: Readonly<Record<Market, string>> = {
  cn: 'A股', us: '美股', hk: '港股', crypto: '加密合约',
}
const MAIN_KEYBOARD = {
  keyboard: [
    [{ text: '📊 行情' }, { text: '📈 K线' }],
    [{ text: '💼 持仓' }, { text: '⭐ 自选' }],
    [{ text: '🛒 下单' }, { text: '☰ 菜单' }],
  ],
  resize_keyboard: true,
  is_persistent: true,
}
const MAIN_MENU = {
  inline_keyboard: [
    [{ text: '📊 行情查询', callback_data: 'menu:quote' }, { text: '📈 K线图', callback_data: 'menu:kline' }],
    [{ text: '⭐ 我的自选', callback_data: 'act:watchlist' }, { text: '💼 我的持仓', callback_data: 'act:positions' }],
    [{ text: '🛒 模拟下单', callback_data: 'menu:order' }, { text: '🔔 告警规则', callback_data: 'menu:rules' }],
    [{ text: '🌙 安静时段', callback_data: 'menu:quiet' }, { text: '🌐 打开 Midas', url: 'https://midastrade.asia' }],
  ],
}

function telegramUrl(env: Env, method: string): string {
  return `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`
}

async function telegramCall(
  env: Env,
  method: string,
  body: Record<string, unknown> | FormData,
): Promise<void> {
  const form = body instanceof FormData
  const response = await fetch(telegramUrl(env, method), {
    method: 'POST',
    ...(form ? {} : { headers: { 'content-type': 'application/json' } }),
    body: form ? body : JSON.stringify(body),
    signal: AbortSignal.timeout(65_000),
  })
  if (!response.ok) throw new Error(`Telegram ${method} HTTP ${response.status}`)
  const result = (await response.json()) as { ok?: boolean; description?: string }
  if (!result.ok) throw new Error(result.description || `Telegram ${method} failed`)
}

export async function telegramSend(
  env: Env,
  chatId: string,
  text: string,
  replyMarkup?: TelegramMarkup,
): Promise<void> {
  await telegramCall(env, 'sendMessage', {
    chat_id: chatId,
    text: text.slice(0, 4_096),
    ...(replyMarkup ? { reply_markup: replyMarkup } : {}),
  })
}

async function answerCallback(env: Env, callbackId: string): Promise<void> {
  await telegramCall(env, 'answerCallbackQuery', { callback_query_id: callbackId })
}

export async function sendTelegramWelcome(
  env: Env,
  chatId: string,
  bindingSucceeded = false,
): Promise<void> {
  await telegramSend(
    env,
    chatId,
    bindingSucceeded
      ? 'Midas Trading 绑定成功。行情、自选、持仓、模拟交易和提醒已连接到云端账户。'
      : 'Midas Trading 云端交易助手。可查行情与 K 线、管理提醒，并操作同账户的模拟交易。',
    MAIN_KEYBOARD,
  )
  await telegramSend(env, chatId, '请选择功能：', MAIN_MENU)
}

export const TELEGRAM_COMMANDS = [
  { command: 'start', description: '打开 Midas Trading' },
  { command: 'menu', description: '显示主菜单' },
  { command: 'price', description: '查询行情，例如 /price BTC' },
]

async function boundUser(env: Env, chatId: string): Promise<string | null> {
  const row = await env.DB.prepare(
    'SELECT user_id FROM notification_configs WHERE tg_chat_id = ?',
  ).bind(chatId).first<{ user_id: string }>()
  return row?.user_id ?? null
}

async function ensureSession(env: Env, chatId: string): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO telegram_bot_sessions (chat_id, updated_at)
     VALUES (?, ?) ON CONFLICT(chat_id) DO NOTHING`,
  ).bind(chatId, Date.now()).run()
}

async function rateAllowed(
  env: Env,
  chatId: string,
  kind: 'command' | 'order',
): Promise<boolean> {
  await ensureSession(env, chatId)
  const now = Date.now()
  const limit = kind === 'command' ? COMMAND_LIMIT : ORDER_LIMIT
  const windowColumn = `${kind}_window_started_at`
  const countColumn = `${kind}_count`
  const result = await env.DB.prepare(
    `UPDATE telegram_bot_sessions SET
       ${countColumn} = CASE WHEN ${windowColumn} <= ? THEN 1 ELSE ${countColumn} + 1 END,
       ${windowColumn} = CASE WHEN ${windowColumn} <= ? THEN ? ELSE ${windowColumn} END,
       updated_at = ?
     WHERE chat_id = ? AND (${windowColumn} <= ? OR ${countColumn} < ?)`,
  ).bind(now - WINDOW_MS, now - WINDOW_MS, now, now, chatId, now - WINDOW_MS, limit).run()
  return result.meta.changes === 1
}

async function loadState(env: Env, chatId: string): Promise<SessionState> {
  const row = await env.DB.prepare(
    'SELECT state_json, state_expires_at FROM telegram_bot_sessions WHERE chat_id = ?',
  ).bind(chatId).first<{ state_json: string; state_expires_at: number }>()
  if (!row || row.state_expires_at <= Date.now()) return {}
  try { return JSON.parse(row.state_json) as SessionState } catch { return {} }
}

async function saveState(env: Env, chatId: string, state: SessionState): Promise<void> {
  await ensureSession(env, chatId)
  await env.DB.prepare(
    `UPDATE telegram_bot_sessions
     SET state_json = ?, state_expires_at = ?, updated_at = ? WHERE chat_id = ?`,
  ).bind(JSON.stringify(state), Date.now() + SESSION_TTL_MS, Date.now(), chatId).run()
}

async function clearState(env: Env, chatId: string): Promise<void> {
  await saveState(env, chatId, {})
}

async function consumeOrderConfirmation(
  env: Env,
  chatId: string,
): Promise<SessionState | null> {
  const row = await env.DB.prepare(
    'SELECT state_json, state_expires_at FROM telegram_bot_sessions WHERE chat_id = ?',
  ).bind(chatId).first<{ state_json: string; state_expires_at: number }>()
  if (!row || row.state_expires_at <= Date.now()) return null
  let state: SessionState
  try { state = JSON.parse(row.state_json) as SessionState } catch { return null }
  if (state.action !== 'order_confirm') return null
  const now = Date.now()
  const consumed = await env.DB.prepare(
    `UPDATE telegram_bot_sessions
     SET state_json = '{}', state_expires_at = 0, updated_at = ?
     WHERE chat_id = ? AND state_json = ? AND state_expires_at > ?`,
  ).bind(now, chatId, row.state_json, now).run()
  return consumed.meta.changes === 1 ? state : null
}

function normalizeSymbol(raw: string, market: Market): string {
  const value = raw.trim().toUpperCase().replace(/^\$/u, '')
  if (market === 'crypto') {
    const base = value.replace(/[-_/]?(USDT|USD)$/u, '')
    return `${base}/USDT`
  }
  if (market === 'hk' && /^\d{1,5}$/u.test(value)) return value.padStart(5, '0')
  return value
}

function inferMarket(raw: string): Market {
  const value = raw.trim().toUpperCase().replace(/^\$/u, '')
  if (/^\d{6}$/u.test(value)) return 'cn'
  if (/^\d{1,5}$/u.test(value)) return 'hk'
  if (/(?:USDT|USD)$/u.test(value) || COMMON_CRYPTO.has(value)) return 'crypto'
  return 'us'
}

function marketPicker(action: 'quote' | 'kline' | 'order_symbol'): TelegramMarkup {
  const prefix = action === 'order_symbol' ? 'omkt' : `ask:${action}`
  return {
    inline_keyboard: [
      [{ text: 'A股', callback_data: `${prefix}:cn` }, { text: '美股', callback_data: `${prefix}:us` }],
      [{ text: '港股', callback_data: `${prefix}:hk` }, { text: '加密', callback_data: `${prefix}:crypto` }],
      [{ text: '返回菜单', callback_data: 'menu:main' }],
    ],
  }
}

function detailUrl(env: Env, market: Market, symbol: string): string {
  const path = market === 'crypto' ? '/crypto-preview' : `/${market}-preview`
  const url = new URL(path, env.PUBLIC_WEB_URL || 'https://midastrade.asia')
  url.searchParams.set('symbol', symbol)
  return url.toString()
}

async function quote(market: Market, symbol: string) {
  const normalized = normalizeSymbol(symbol, market)
  const result = await fetchMarketKlines({
    symbol: normalized,
    market,
    period: '5m',
    instrument: market === 'crypto' ? 'perp' : 'spot',
    limit: 289,
  })
  const last = result.items.at(-1)
  const prior = result.items.at(-2)
  const dayStart = result.items.at(Math.max(0, result.items.length - 288))
  if (!last) throw new Error('行情暂不可用')
  const change = dayStart?.close ? ((last.close - dayStart.close) / dayStart.close) * 100 : null
  return {
    market,
    symbol: normalized,
    price: last.close,
    change,
    move: prior?.close ? ((last.close - prior.close) / prior.close) * 100 : null,
    high: Math.max(...result.items.slice(-288).map((item) => item.high)),
    low: Math.min(...result.items.slice(-288).map((item) => item.low)),
    source: result.source,
  }
}

function number(value: number, digits = 4): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: digits })
}

async function showQuote(
  env: Env,
  chatId: string,
  market: Market,
  symbol: string,
): Promise<void> {
  const item = await quote(market, symbol)
  const change = item.change === null ? '—' : `${item.change >= 0 ? '+' : ''}${item.change.toFixed(2)}%`
  await telegramSend(
    env,
    chatId,
    `${MARKETS[market]} · ${item.symbol}\n最新价 ${number(item.price, 8)}\n24H涨跌 ${change}\n24H高/低 ${number(item.high, 8)} / ${number(item.low, 8)}\n数据源 ${item.source}`,
    {
      inline_keyboard: [
        [{ text: '📈 K线图', callback_data: `qk:${market}:${item.symbol}` }, { text: '🔄 刷新', callback_data: `qr:${market}:${item.symbol}` }],
        [{ text: '🛒 模拟下单', callback_data: `qo:${market}:${item.symbol}` }, { text: '🌐 网页详情', url: detailUrl(env, market, item.symbol) }],
      ],
    },
  )
}

async function captureChart(env: Env, market: Market, symbol: string): Promise<ArrayBuffer | null> {
  if (!env.BROWSER) return null
  const response = await env.BROWSER.quickAction('screenshot', {
    url: detailUrl(env, market, symbol),
    selector: '[data-social-chart="true"]',
    viewport: { width: 1280, height: 900, deviceScaleFactor: 2 },
    gotoOptions: { waitUntil: 'networkidle2', timeout: 45_000 },
    waitForTimeout: 3_000,
    actionTimeout: 60_000,
    screenshotOptions: { type: 'png', optimizeForSpeed: true },
    cacheTTL: 0,
  })
  return response.ok ? response.arrayBuffer() : null
}

async function showKline(env: Env, chatId: string, market: Market, symbol: string): Promise<void> {
  const normalized = normalizeSymbol(symbol, market)
  await telegramSend(env, chatId, `正在生成 ${normalized} K 线图…`)
  const image = await captureChart(env, market, normalized)
  if (!image) {
    await telegramSend(env, chatId, 'K 线截图暂不可用，可打开网页查看。', {
      inline_keyboard: [[{ text: '打开 K 线', url: detailUrl(env, market, normalized) }]],
    })
    return
  }
  const form = new FormData()
  form.set('chat_id', chatId)
  form.set('caption', `${MARKETS[market]} · ${normalized} · 1H K线`)
  form.set('photo', new Blob([image], { type: 'image/png' }), `${normalized.replace(/\W/gu, '')}.png`)
  await telegramCall(env, 'sendPhoto', form)
}

async function showWatchlist(env: Env, chatId: string, userId: string): Promise<void> {
  const rows = await env.DB.prepare(
    `SELECT symbol, market FROM watchlist_items
     WHERE user_id = ? ORDER BY sort_order, added_at LIMIT 30`,
  ).bind(userId).all<{ symbol: string; market: Market }>()
  if (!rows.results.length) {
    await telegramSend(env, chatId, '自选列表为空，可在网页详情页加入自选。')
    return
  }
  const items = await Promise.all(rows.results.map(async (row) => {
    try {
      const item = await quote(row.market, row.symbol)
      const change = item.change === null ? '—' : `${item.change >= 0 ? '+' : ''}${item.change.toFixed(2)}%`
      return `${row.symbol}  ${number(item.price, 6)}  ${change}`
    } catch { return `${row.symbol}  行情暂不可用` }
  }))
  await telegramSend(env, chatId, `⭐ 我的自选\n${items.join('\n')}`, {
    inline_keyboard: [[{ text: '打开自选', url: new URL('/watchlist', env.PUBLIC_WEB_URL).toString() }]],
  })
}

async function showPositions(env: Env, chatId: string, userId: string): Promise<void> {
  const [spots, perps] = await Promise.all([
    env.DB.prepare(
      `SELECT p.symbol, p.market, p.position_side, p.quantity, p.avg_entry_price
       FROM virtual_positions p JOIN virtual_accounts a ON a.id = p.account_id
       WHERE a.user_id = ? AND p.closed_at IS NULL ORDER BY p.id DESC LIMIT 30`,
    ).bind(userId).all<{ symbol: string; market: Market; position_side: string; quantity: number; avg_entry_price: number }>(),
    env.DB.prepare(
      `SELECT p.symbol, p.side, p.leverage, p.quantity, p.entry_price, p.liquidation_price
       FROM virtual_perp_positions p JOIN virtual_accounts a ON a.id = p.account_id
       WHERE a.user_id = ? AND p.closed_at IS NULL ORDER BY p.id DESC LIMIT 30`,
    ).bind(userId).all<{ symbol: string; side: string; leverage: number; quantity: number; entry_price: number; liquidation_price: number }>(),
  ])
  const lines = [
    ...spots.results.map((row) => `${MARKETS[row.market]} ${row.symbol} ${row.position_side === 'short' ? '空' : '多'} ${number(row.quantity, 6)} @ ${number(row.avg_entry_price, 6)}`),
    ...perps.results.map((row) => `合约 ${row.symbol} ${row.side === 'long' ? '多' : '空'} ${row.leverage}x ${number(row.quantity, 6)} @ ${number(row.entry_price, 6)} 强平 ${number(row.liquidation_price, 6)}`),
  ]
  await telegramSend(env, chatId, lines.length ? `💼 当前模拟持仓\n${lines.join('\n')}` : '当前没有模拟持仓。', {
    inline_keyboard: [[{ text: '打开持仓与订单', url: new URL('/account/positions', env.PUBLIC_WEB_URL).toString() }]],
  })
}

type AlertRule = { id: number; market: Market; symbol: string | null; indicator: string; operator: string; threshold: string; timeframe: string | null; enabled: number }
const INDICATOR_LABELS: Readonly<Record<string, string>> = {
  price: '最新价', price_change_pct: '涨跌幅', volume: '成交量', ma_5: 'MA5', ma_20: 'MA20', ma_60: 'MA60',
  macd_hist: 'MACD柱', rsi_14: 'RSI(14)', boll_pctb: '布林%B', funding_rate: '资金费率',
  open_interest_usd: '合约持仓额', long_short_ratio: '账户多空比', basis_pct: '合约基差',
  chan_buy: '缠论买点', chan_sell: '缠论卖点', fear_greed: '恐贪指数',
  btc_dominance: 'BTC占比', cn_breadth_up_ratio: 'A股上涨占比',
  hk_breadth_up_ratio: '港股上涨占比', sector_change_pct: '板块涨跌', index_change_pct: '指数涨跌',
}
const OPERATOR_LABELS: Readonly<Record<string, string>> = { gt: '>', gte: '≥', lt: '<', lte: '≤' }

async function showRules(env: Env, chatId: string, userId: string): Promise<void> {
  const rows = await env.DB.prepare(
    `SELECT id, market, symbol, indicator, operator, threshold, timeframe, enabled
     FROM alert_rules WHERE user_id = ? ORDER BY created_at LIMIT 50`,
  ).bind(userId).all<AlertRule>()
  const lines = rows.results.map((row) => `${row.enabled ? '✅' : '⏸'} #${row.id} ${row.symbol ?? MARKETS[row.market]} ${INDICATOR_LABELS[row.indicator] ?? row.indicator} ${OPERATOR_LABELS[row.operator] ?? row.operator} ${row.threshold}${row.timeframe ? ` · ${row.timeframe}` : ''}`)
  const buttons = rows.results.slice(0, 20).map((row) => [{ text: `${row.enabled ? '暂停' : '启用'} #${row.id}`, callback_data: `rules:toggle:${row.id}` }])
  buttons.push([{ text: '应用推荐规则', callback_data: 'rules:apply' }])
  await telegramSend(env, chatId, lines.length ? `🔔 告警规则\n${lines.join('\n')}` : '尚未配置告警规则。', { inline_keyboard: buttons })
}

async function applyRecommendedRules(env: Env, userId: string): Promise<number> {
  const recommendations = [
    ['us', 'NVDA', 'rsi_14', 'gt', '75', '1d'], ['us', 'NVDA', 'rsi_14', 'lt', '25', '1d'],
    ['cn', '600519', 'rsi_14', 'gt', '75', '1d'], ['cn', '600519', 'rsi_14', 'lt', '25', '1d'],
    ['crypto', 'BTC/USDT', 'rsi_14', 'gt', '80', '1d'], ['crypto', 'BTC/USDT', 'rsi_14', 'lt', '20', '1d'],
  ] as const
  const existing = await env.DB.prepare(
    'SELECT market, symbol, indicator, operator, threshold FROM alert_rules WHERE user_id = ?',
  ).bind(userId).all<{ market: string; symbol: string; indicator: string; operator: string; threshold: string }>()
  const keys = new Set(existing.results.map((row) => [row.market, row.symbol, row.indicator, row.operator, row.threshold].join('|')))
  const now = Date.now()
  const statements = recommendations.filter((row) => !keys.has(row.slice(0, 5).join('|'))).map((row) => env.DB.prepare(
    `INSERT INTO alert_rules (user_id, market, symbol, indicator, operator, threshold, timeframe, cooldown_sec, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, 300, ?, ?)`,
  ).bind(userId, ...row, now, now))
  if (statements.length) await env.DB.batch(statements)
  return statements.length
}

async function showQuiet(env: Env, chatId: string, userId: string): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT quiet_hours_enabled, quiet_hours_start, quiet_hours_end, quiet_hours_tz
     FROM notification_configs WHERE user_id = ?`,
  ).bind(userId).first<{ quiet_hours_enabled: number; quiet_hours_start: number; quiet_hours_end: number; quiet_hours_tz: string }>()
  if (!row) return
  await telegramSend(env, chatId, `🌙 安静时段\n状态 ${row.quiet_hours_enabled ? '开启' : '关闭'}\n时段 ${String(row.quiet_hours_start).padStart(2, '0')}:00–${String(row.quiet_hours_end).padStart(2, '0')}:00\n时区 ${row.quiet_hours_tz}`, {
    inline_keyboard: [
      [{ text: row.quiet_hours_enabled ? '关闭' : '开启', callback_data: 'quiet:toggle' }],
      [{ text: '开始 -1h', callback_data: 'quiet:s-' }, { text: '开始 +1h', callback_data: 'quiet:s+' }],
      [{ text: '结束 -1h', callback_data: 'quiet:e-' }, { text: '结束 +1h', callback_data: 'quiet:e+' }],
    ],
  })
}

function directionMenu(market: Market): TelegramMarkup {
  const rows = market === 'crypto'
    ? [['开多', 'open_long'], ['开空', 'open_short'], ['平仓', 'close']]
    : market === 'us'
      ? [['买入', 'buy'], ['卖出', 'sell'], ['卖空', 'short'], ['平空', 'cover']]
      : [['买入', 'buy'], ['卖出', 'sell']]
  return { inline_keyboard: rows.map(([text, value]) => [{ text, callback_data: `odir:${value}` }]) }
}

type Preset = { perp_leverage: number; perp_notional_usdt: string; perp_margin_mode: 'isolated' | 'cross'; spot_notional_cny: string; spot_notional_usd: string }
async function preset(env: Env, userId: string): Promise<Preset> {
  const row = await env.DB.prepare('SELECT * FROM bot_order_presets WHERE user_id = ?').bind(userId).first<Preset>()
  return row ?? { perp_leverage: 3, perp_notional_usdt: '100', perp_margin_mode: 'isolated', spot_notional_cny: '10000', spot_notional_usd: '1000' }
}

async function orderPreview(env: Env, userId: string, state: SessionState, direction: string): Promise<string> {
  const market = state.market!
  const symbol = normalizeSymbol(state.symbol!, market)
  const item = await quote(market, symbol)
  const p = await preset(env, userId)
  if (direction === 'close' || direction === 'sell' || direction === 'cover') {
    return `${MARKETS[market]} ${symbol}\n方向 ${direction}\n按当前全部模拟持仓执行市价平仓\n参考价 ${number(item.price, 8)}`
  }
  const notional = market === 'crypto' ? Number(p.perp_notional_usdt) : market === 'cn' ? Number(p.spot_notional_cny) : market === 'hk' ? 50_000 : Number(p.spot_notional_usd)
  const quantity = notional / item.price
  return `${MARKETS[market]} ${symbol}\n方向 ${direction}\n预设名义金额 ${number(notional, 2)} ${market === 'crypto' ? 'USDT' : market === 'cn' ? 'CNY' : market === 'hk' ? 'HKD' : 'USD'}\n预计数量 ${number(quantity, 8)}\n参考价 ${number(item.price, 8)}${market === 'crypto' ? `\n杠杆 ${p.perp_leverage}x · ${p.perp_margin_mode}` : ''}`
}

async function executeOrder(env: Env, userId: string, state: SessionState): Promise<Record<string, unknown>> {
  const market = state.market!
  const symbol = normalizeSymbol(state.symbol!, market)
  const direction = state.direction!
  const p = await preset(env, userId)
  if (market === 'crypto') {
    const notional = Number(p.perp_notional_usdt)
    return executePerpOrder(env, {
      userId, symbol,
      intent: direction as 'open_long' | 'open_short' | 'close',
      leverage: p.perp_leverage,
      ...(direction === 'close' ? {} : { margin: notional / p.perp_leverage }),
      closeAll: true,
      marginMode: p.perp_margin_mode,
    })
  }
  const account = await env.DB.prepare(
    'SELECT id FROM virtual_accounts WHERE user_id = ? AND market = ?',
  ).bind(userId, market).first<{ id: number }>()
  if (!account) throw new Error('请先在网页激活对应市场的模拟账户')
  const positionSide = direction === 'short' || direction === 'cover' ? 'short' : 'long'
  const side = direction === 'buy' || direction === 'cover' ? 'buy' : 'sell'
  let quantity: number
  const closes = direction === 'sell' || direction === 'cover'
  if (closes) {
    const position = await env.DB.prepare(
      `SELECT quantity FROM virtual_positions
       WHERE account_id = ? AND symbol = ? AND position_side = ? AND closed_at IS NULL`,
    ).bind(account.id, symbol, positionSide).first<{ quantity: number }>()
    if (!position) throw new Error('未找到可平模拟持仓')
    quantity = position.quantity
  } else {
    const item = await quote(market, symbol)
    const notional = market === 'cn' ? Number(p.spot_notional_cny) : market === 'hk' ? 50_000 : Number(p.spot_notional_usd)
    quantity = notional / item.price
  }
  return executeSpotOrder(env, { userId, symbol, market, side, positionSide, quantity, source: 'telegram_bot' })
}

function extractChat(update: TelegramUpdate): { chatId: string | null; callbackId: string | null; data: string; text: string } {
  const callback = update.callback_query
  const rawChat = callback?.message?.chat?.id ?? update.message?.chat?.id
  return {
    chatId: typeof rawChat === 'number' || typeof rawChat === 'string' ? String(rawChat) : null,
    callbackId: typeof callback?.id === 'string' ? callback.id : null,
    data: typeof callback?.data === 'string' ? callback.data : '',
    text: typeof update.message?.text === 'string' ? update.message.text.trim() : '',
  }
}

async function handleCallback(env: Env, chatId: string, userId: string, data: string): Promise<void> {
  if (data === 'menu:main') return sendTelegramWelcome(env, chatId)
  if (data === 'menu:quote' || data === 'menu:kline') {
    const action = data.endsWith('quote') ? 'quote' : 'kline'
    await telegramSend(env, chatId, '请选择市场：', marketPicker(action))
    return
  }
  if (data === 'menu:order') {
    await telegramSend(env, chatId, '请选择模拟交易市场：', marketPicker('order_symbol'))
    return
  }
  if (data === 'act:watchlist') return showWatchlist(env, chatId, userId)
  if (data === 'act:positions') return showPositions(env, chatId, userId)
  if (data === 'menu:rules') return showRules(env, chatId, userId)
  if (data === 'menu:quiet') return showQuiet(env, chatId, userId)

  const ask = data.match(/^ask:(quote|kline):(cn|us|hk|crypto)$/u)
  if (ask?.[1] && ask[2]) {
    await saveState(env, chatId, { action: ask[1] as 'quote' | 'kline', market: ask[2] as Market })
    await telegramSend(env, chatId, `请输入${MARKETS[ask[2] as Market]}代码或交易对：`)
    return
  }
  const orderMarket = data.match(/^omkt:(cn|us|hk|crypto)$/u)
  if (orderMarket?.[1]) {
    await saveState(env, chatId, { action: 'order_symbol', market: orderMarket[1] as Market })
    await telegramSend(env, chatId, `请输入${MARKETS[orderMarket[1] as Market]}代码或交易对：`)
    return
  }
  const quoteAction = data.match(/^(qr|qk|qo):(cn|us|hk|crypto):(.+)$/u)
  if (quoteAction?.[1] && quoteAction[2] && quoteAction[3]) {
    const market = quoteAction[2] as Market
    if (quoteAction[1] === 'qr') return showQuote(env, chatId, market, quoteAction[3])
    if (quoteAction[1] === 'qk') return showKline(env, chatId, market, quoteAction[3])
    await saveState(env, chatId, { action: 'order_symbol', market, symbol: quoteAction[3] })
    await telegramSend(env, chatId, '请选择模拟交易方向：', directionMenu(market))
    return
  }
  const direction = data.match(/^odir:(open_long|open_short|close|buy|sell|short|cover)$/u)
  if (direction?.[1]) {
    const state = await loadState(env, chatId)
    if (!state.market || !state.symbol) throw new Error('下单会话已过期，请重新选择市场和标的')
    const preview = await orderPreview(env, userId, state, direction[1])
    await saveState(env, chatId, { ...state, action: 'order_confirm', direction: direction[1], preview })
    await telegramSend(env, chatId, `请再次确认：\n${preview}\n\n仅执行模拟交易，不会产生真实资产交易。`, {
      inline_keyboard: [[{ text: '确认模拟下单', callback_data: 'ordok' }, { text: '取消', callback_data: 'ordno' }]],
    })
    return
  }
  if (data === 'ordno') {
    await clearState(env, chatId)
    await telegramSend(env, chatId, '已取消模拟下单。')
    return
  }
  if (data === 'ordok') {
    if (!(await rateAllowed(env, chatId, 'order'))) throw new Error('模拟下单过于频繁，请稍后再试')
    const state = await consumeOrderConfirmation(env, chatId)
    if (!state) throw new Error('确认会话已过期，请重新下单')
    const result = await executeOrder(env, userId, state)
    await telegramSend(env, chatId, `✅ 模拟订单已成交\n${state.preview ?? ''}\n成交价 ${String(result.price ?? '—')}\n订单 #${String(result.id ?? '—')}`)
    return
  }
  const toggle = data.match(/^rules:toggle:(\d+)$/u)
  if (toggle?.[1]) {
    const row = await env.DB.prepare('SELECT enabled FROM alert_rules WHERE id = ? AND user_id = ?').bind(Number(toggle[1]), userId).first<{ enabled: number }>()
    if (!row) throw new Error('规则不存在')
    await env.DB.prepare('UPDATE alert_rules SET enabled = ?, updated_at = ? WHERE id = ? AND user_id = ?').bind(row.enabled ? 0 : 1, Date.now(), Number(toggle[1]), userId).run()
    return showRules(env, chatId, userId)
  }
  if (data === 'rules:apply') {
    const created = await applyRecommendedRules(env, userId)
    await telegramSend(env, chatId, created ? `已新增 ${created} 条推荐规则。` : '推荐规则已经存在。')
    return showRules(env, chatId, userId)
  }
  if (data.startsWith('quiet:')) {
    const row = await env.DB.prepare('SELECT quiet_hours_enabled, quiet_hours_start, quiet_hours_end FROM notification_configs WHERE user_id = ?').bind(userId).first<{ quiet_hours_enabled: number; quiet_hours_start: number; quiet_hours_end: number }>()
    if (!row) throw new Error('通知配置不存在')
    let enabled = row.quiet_hours_enabled
    let start = row.quiet_hours_start
    let end = row.quiet_hours_end
    if (data === 'quiet:toggle') enabled = enabled ? 0 : 1
    if (data === 'quiet:s+') start = (start + 1) % 24
    if (data === 'quiet:s-') start = (start + 23) % 24
    if (data === 'quiet:e+') end = (end + 1) % 24
    if (data === 'quiet:e-') end = (end + 23) % 24
    await env.DB.prepare('UPDATE notification_configs SET quiet_hours_enabled = ?, quiet_hours_start = ?, quiet_hours_end = ?, updated_at = ? WHERE user_id = ?').bind(enabled, start, end, Date.now(), userId).run()
    return showQuiet(env, chatId, userId)
  }
  await telegramSend(env, chatId, '该操作已过期，请重新打开菜单。', MAIN_MENU)
}

async function handleText(env: Env, chatId: string, userId: string, text: string): Promise<void> {
  if (text === '/start' || text === '/menu' || text === '☰ 菜单') return sendTelegramWelcome(env, chatId)
  if (text === '📊 行情') return telegramSend(env, chatId, '请选择市场：', marketPicker('quote'))
  if (text === '📈 K线') return telegramSend(env, chatId, '请选择市场：', marketPicker('kline'))
  if (text === '💼 持仓') return showPositions(env, chatId, userId)
  if (text === '⭐ 自选') return showWatchlist(env, chatId, userId)
  if (text === '🛒 下单') return telegramSend(env, chatId, '请选择模拟交易市场：', marketPicker('order_symbol'))
  if (text.startsWith('/price')) {
    const symbol = text.slice('/price'.length).trim()
    if (!symbol) return telegramSend(env, chatId, '请选择市场：', marketPicker('quote'))
    return showQuote(env, chatId, inferMarket(symbol), symbol)
  }
  const state = await loadState(env, chatId)
  if (state.action === 'quote' && state.market) {
    await clearState(env, chatId)
    return showQuote(env, chatId, state.market, text)
  }
  if (state.action === 'kline' && state.market) {
    await clearState(env, chatId)
    return showKline(env, chatId, state.market, text)
  }
  if (state.action === 'order_symbol' && state.market) {
    const symbol = normalizeSymbol(text, state.market)
    await saveState(env, chatId, { action: 'order_symbol', market: state.market, symbol })
    return telegramSend(env, chatId, '请选择模拟交易方向：', directionMenu(state.market))
  }
  if (/^[A-Za-z][A-Za-z0-9._/-]{0,20}$/u.test(text) || /^\$[A-Za-z][A-Za-z0-9._/-]{0,20}$/u.test(text)) {
    return showQuote(env, chatId, inferMarket(text), text)
  }
  await telegramSend(env, chatId, '未识别该指令。可发送代码查询行情，或打开菜单选择功能。', MAIN_MENU)
}

export async function handleTelegramBotUpdate(env: Env, body: Record<string, unknown>): Promise<void> {
  const update = body as TelegramUpdate
  const { chatId, callbackId, data, text } = extractChat(update)
  if (!chatId) return
  if (callbackId) await answerCallback(env, callbackId)
  const userId = await boundUser(env, chatId)
  if (!userId) {
    await telegramSend(env, chatId, '此机器人尚未绑定 Midas Trading 账户，请在网页「通知与提醒」中重新绑定。')
    return
  }
  if (!(await rateAllowed(env, chatId, 'command'))) {
    await telegramSend(env, chatId, '操作过于频繁，请稍后再试。')
    return
  }
  try {
    if (data) await handleCallback(env, chatId, userId, data)
    else if (text) await handleText(env, chatId, userId, text)
  } catch (error) {
    const message = error instanceof Error ? error.message : '操作失败'
    await telegramSend(env, chatId, `操作未完成：${message}`)
  }
}
