import { fetchCryptoMarketScan } from './crypto-market'
import { HttpError, jsonResponse } from './http'
import { fetchMarketKlines, type Kline } from './market'
import { deliverUserNotification } from './notifications'

const LABELS = {
  trend_up: '三线齐上·上升结构',
  trend_down: '三线齐跌·下降结构',
  range: '三线走平·震荡结构',
  breakout_up: '带宽开口·向上',
  squeeze: '带宽收口·方向未明',
  breakdown: '带宽开口·向下',
} as const

type BollState = keyof typeof LABELS

export type BollScanItem = Readonly<{
  symbol: string
  state: BollState
  state_label: string
  bias: '偏多' | '中性' | '偏空'
  pct_b: number
  zone_label: string
  bandwidth: number
  close: number
  mid: number
  upper: number
  lower: number
  change_pct_24h: number | null
  funding_rate: number | null
  transition: boolean
  transition_from: string | null
}>

type BollScanRow = Omit<BollScanItem, 'transition'> & Readonly<{
  transition: number
  last_transition_sent_at: number | null
  updated_at: number
}>

function round(value: number, digits: number): number {
  return Number(value.toFixed(digits))
}

function bollAt(closes: number[], end: number): [number, number, number] | null {
  const values = closes.slice(end - 20, end)
  if (values.length < 20) return null
  const mid = values.reduce((sum, value) => sum + value, 0) / values.length
  const variance = values.reduce((sum, value) => sum + (value - mid) ** 2, 0) /
    (values.length - 1)
  const deviation = Math.sqrt(variance)
  return [mid, mid + 2 * deviation, mid - 2 * deviation]
}

export function classifyBoll(klines: readonly Kline[]): BollScanItem | null {
  if (klines.length < 24) return null
  const closes = klines.map((item) => item.close)
  const current = bollAt(closes, closes.length)
  const previous = bollAt(closes, closes.length - 4)
  if (!current || !previous) return null
  const [mid, upper, lower] = current
  const [previousMid, previousUpper, previousLower] = previous
  const width = upper - lower
  if (width <= 0 || mid <= 0 || previousMid <= 0) return null

  const close = closes.at(-1)!
  const pctB = (close - lower) / width
  const bandwidth = width / mid
  const previousBandwidth = (previousUpper - previousLower) / previousMid
  const slope = (mid - previousMid) / previousMid
  const bandwidthChange = previousBandwidth
    ? (bandwidth - previousBandwidth) / previousBandwidth
    : 0
  let state: BollState
  if (bandwidthChange <= -0.1) state = 'squeeze'
  else if (bandwidthChange >= 0.1) {
    if (slope < -0.003 || pctB < 0.2) state = 'breakdown'
    else if (slope > 0.003 || pctB > 0.8) state = 'breakout_up'
    else state = 'range'
  } else if (slope > 0.003) state = 'trend_up'
  else if (slope < -0.003) state = 'trend_down'
  else state = 'range'

  const bias = state === 'trend_up' || state === 'breakout_up'
    ? '偏多'
    : state === 'trend_down' || state === 'breakdown'
      ? '偏空'
      : state === 'range' && pctB < 0.2
        ? '偏多'
        : state === 'range' && pctB > 0.8
          ? '偏空'
          : '中性'
  const zone = pctB > 1
    ? '破上轨'
    : pctB > 0.8
      ? '近上轨'
      : pctB < 0
        ? '破下轨'
        : pctB < 0.2
          ? '近下轨'
          : pctB >= 0.4 && pctB <= 0.6
            ? '近中轨'
            : '中间'
  return {
    symbol: '',
    state,
    state_label: LABELS[state],
    bias,
    pct_b: round(pctB, 3),
    zone_label: zone,
    bandwidth: round(bandwidth, 4),
    close,
    mid: round(mid, 6),
    upper: round(upper, 6),
    lower: round(lower, 6),
    change_pct_24h: null,
    funding_rate: null,
    transition: false,
    transition_from: null,
  }
}

function publicItem(row: BollScanRow): BollScanItem {
  const { last_transition_sent_at: _sent, updated_at: _updated, ...item } = row
  return { ...item, transition: row.transition === 1 }
}

async function scanRows(db: D1Database): Promise<BollScanRow[]> {
  const result = await db
    .prepare(
      `SELECT * FROM telegram_market_scan_states
       WHERE updated_at >= ? ORDER BY ABS(change_pct_24h) DESC`,
    )
    .bind(Date.now() - 30 * 60_000)
    .all<BollScanRow>()
  return result.results
}

function normalizedSymbol(value: string): string {
  const symbol = value.trim().toUpperCase().replace('/', '')
  if (!/^[A-Z0-9]{2,20}USDT$/u.test(symbol)) {
    throw new HttpError(400, 'symbol 格式无效')
  }
  return symbol
}

async function computeItem(symbol: string): Promise<BollScanItem | null> {
  const normalized = normalizedSymbol(symbol)
  const result = await fetchMarketKlines({
    symbol: `${normalized.slice(0, -4)}/USDT`,
    market: 'crypto',
    period: '15m',
    instrument: 'perp',
    limit: 30,
  })
  const item = classifyBoll(result.items)
  return item ? { ...item, symbol: normalized } : null
}

function digestGroup(item: BollScanItem): '偏多' | '中性' | '偏空' {
  if (item.bias === '偏多' && item.pct_b > 0.6) return '偏多'
  if (item.bias === '偏空' && item.pct_b < 0.4) return '偏空'
  return '中性'
}

export function buildBollDigest(
  items: readonly BollScanItem[],
  label: string,
): string | null {
  if (items.length === 0) return null
  const groups = [
    ['📈 偏多', '偏多', (item: BollScanItem) => -item.pct_b],
    ['➖ 中性', '中性', (item: BollScanItem) => -Math.abs(item.change_pct_24h ?? 0)],
    ['📉 偏空', '偏空', (item: BollScanItem) => item.pct_b],
  ] as const
  const lines = [`📊 做T定时全景 · ${label}`]
  for (const [title, group, score] of groups) {
    const members = items.filter((item) => digestGroup(item) === group)
    if (members.length === 0) continue
    lines.push(`${title}（${members.length}）`)
    lines.push(...[...members]
      .sort((left, right) => score(left) - score(right))
      .slice(0, 5)
      .map((item) =>
        `${item.symbol}｜${item.state_label} · ${item.zone_label}（%B=${item.pct_b.toFixed(2)}） · ${(item.change_pct_24h ?? 0).toFixed(1)}%`,
      ))
  }
  return lines.length > 1 ? lines.join('\n') : null
}

async function subscribers(
  db: D1Database,
  field: 'dott_digest_enabled' | 'dott_transition_enabled',
): Promise<string[]> {
  // ponytail: twenty users fit one Free-plan scan invocation; move fan-out to a Queue when this ceiling is reached.
  const result = await db
    .prepare(
      `SELECT user_id FROM notification_configs
       WHERE ${field} = 1
         AND (tg_chat_id IS NOT NULL OR feishu_open_id IS NOT NULL)
       ORDER BY updated_at LIMIT 20`,
    )
    .all<{ user_id: string }>()
  return result.results.map((row) => row.user_id)
}

async function notifySubscribers(
  env: Env,
  field: 'dott_digest_enabled' | 'dott_transition_enabled',
  title: string,
  body: string,
  dedupe: string,
): Promise<number> {
  const userIds = await subscribers(env.DB, field)
  for (const userId of userIds) {
    await deliverUserNotification(env, {
      userId,
      category: field === 'dott_digest_enabled' ? 'dott_digest' : 'dott_transition',
      title,
      body,
      dedupeKey: `${dedupe}:${userId}`,
    })
  }
  return userIds.length
}

async function refreshScan(env: Env, scheduledTime: number): Promise<void> {
  const [market, stored] = await Promise.all([
    fetchCryptoMarketScan(14),
    env.DB.prepare('SELECT * FROM telegram_market_scan_states').all<BollScanRow>(),
  ])
  const previous = new Map(stored.results.map((row) => [row.symbol, row]))
  const computed = await Promise.allSettled(market.map(async (ticker) => {
    const item = await computeItem(ticker.symbol)
    if (!item) return null
    const symbol = normalizedSymbol(ticker.symbol)
    const old = previous.get(symbol)
    const transition = Boolean(old && old.state !== item.state)
    return {
      ...item,
      symbol,
      change_pct_24h: ticker.change_pct_24h,
      transition,
      transition_from: transition ? old?.state_label ?? null : null,
      last_transition_sent_at: old?.last_transition_sent_at ?? null,
      updated_at: scheduledTime,
    }
  }))
  const rows = computed.flatMap((result) =>
    result.status === 'fulfilled' && result.value ? [result.value] : [],
  )
  if (rows.length === 0) throw new Error('布林扫描没有生成有效快照')
  await env.DB.batch(rows.map((row) => env.DB.prepare(
    `INSERT INTO telegram_market_scan_states
      (symbol, state, state_label, bias, pct_b, zone_label, bandwidth, close,
       mid, upper, lower, change_pct_24h, funding_rate, transition,
       transition_from, last_transition_sent_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(symbol) DO UPDATE SET
       state = excluded.state, state_label = excluded.state_label,
       bias = excluded.bias, pct_b = excluded.pct_b,
       zone_label = excluded.zone_label, bandwidth = excluded.bandwidth,
       close = excluded.close, mid = excluded.mid, upper = excluded.upper,
       lower = excluded.lower, change_pct_24h = excluded.change_pct_24h,
       funding_rate = excluded.funding_rate, transition = excluded.transition,
       transition_from = excluded.transition_from, updated_at = excluded.updated_at`,
  ).bind(
    row.symbol, row.state, row.state_label, row.bias, row.pct_b,
    row.zone_label, row.bandwidth, row.close, row.mid, row.upper, row.lower,
    row.change_pct_24h, row.funding_rate, row.transition ? 1 : 0,
    row.transition_from, row.last_transition_sent_at, row.updated_at,
  )))

  const transitions = rows
    .filter((row) => row.transition &&
      (!row.last_transition_sent_at || scheduledTime - row.last_transition_sent_at >= 4 * 60 * 60_000))
    .sort((left, right) =>
      Math.abs(right.pct_b - 0.5) - Math.abs(left.pct_b - 0.5),
    )
    .slice(0, 5)
  if (transitions.length === 0) return
  const body = transitions.map((item) =>
    `${item.bias === '偏多' ? '📈' : item.bias === '偏空' ? '📉' : '➖'} ${item.symbol}｜${item.transition_from} → ${item.state_label} · %B=${item.pct_b.toFixed(2)}`,
  ).join('\n')
  const notified = await notifySubscribers(
    env,
    'dott_transition_enabled',
    `布林结构转换（${transitions.length}）`,
    body,
    `boll-transition:${scheduledTime}`,
  )
  if (notified > 0) {
    await env.DB.batch(transitions.map((item) => env.DB
      .prepare('UPDATE telegram_market_scan_states SET last_transition_sent_at = ? WHERE symbol = ?')
      .bind(scheduledTime, item.symbol)))
  }
}

async function sendHourlyDigest(env: Env, scheduledTime: number): Promise<void> {
  const rows = await scanRows(env.DB)
  const label = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Singapore',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(scheduledTime))
  const body = buildBollDigest(rows.map(publicItem), label)
  if (!body) return
  await notifySubscribers(
    env,
    'dott_digest_enabled',
    'Midas Trading 市场扫描',
    body,
    `boll-digest:${new Date(scheduledTime).toISOString().slice(0, 13)}`,
  )
}

export async function runTelegramMarketCron(env: Env, scheduledTime: number): Promise<void> {
  const minute = new Date(scheduledTime).getUTCMinutes()
  if (minute % 15 === 5) await refreshScan(env, scheduledTime)
  if (minute === 0) await sendHourlyDigest(env, scheduledTime)
}

export async function handleBollScanRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (path !== '/api/v1/crypto/boll-scan' &&
      !path.startsWith('/api/v1/crypto/boll-structure/')) return null
  if (request.method !== 'GET') {
    return jsonResponse({ detail: 'Method not allowed' }, 405, requestId, request.method)
  }
  if (path === '/api/v1/crypto/boll-scan') {
    const rows = await scanRows(env.DB)
    const response = jsonResponse({
      as_of: rows[0] ? new Date(rows[0].updated_at).toISOString() : null,
      count: rows.length,
      disclaimer: '',
      items: rows.map(publicItem),
    }, 200, requestId, request.method)
    response.headers.set('cache-control', 'public, max-age=15, s-maxage=60')
    return response
  }
  const encoded = path.slice('/api/v1/crypto/boll-structure/'.length)
  const symbol = normalizedSymbol(decodeURIComponent(encoded))
  const row = await env.DB
    .prepare('SELECT * FROM telegram_market_scan_states WHERE symbol = ?')
    .bind(symbol)
    .first<BollScanRow>()
  let item = row ? publicItem(row) : null
  let source: 'snapshot' | 'computed' | 'none' = row ? 'snapshot' : 'none'
  if (!item) {
    try {
      item = await computeItem(symbol)
      if (item) source = 'computed'
    } catch {
      item = null
    }
  }
  return jsonResponse({
    symbol,
    available: Boolean(item),
    source,
    layer: '布林结构',
    as_of: row ? new Date(row.updated_at).toISOString() : item ? new Date().toISOString() : null,
    item,
    disclaimer: '',
  }, 200, requestId, request.method)
}
