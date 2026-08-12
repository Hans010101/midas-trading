import { authenticate } from './auth'
import { HttpError, jsonResponse, readJsonObject } from './http'
import { fetchMarketKlines } from './market'
import { executePerpOrder, executeSpotOrder } from './virtual-trading'

type ConditionalRow = Readonly<{
  id: number
  user_id: string
  symbol: string
  market: string
  order_kind: 'limit' | 'stop_loss' | 'take_profit'
  side: 'buy' | 'sell'
  position_side: 'long' | 'short'
  trigger_price: number
  quantity: number | null
  leverage: number | null
  margin: number | null
  margin_mode: 'isolated' | 'cross' | null
  expires_at: number | null
  status: 'active' | 'triggered' | 'cancelled' | 'expired' | 'failed'
  triggered_order_id: number | null
  note: string | null
  created_at: number
  updated_at: number
}>

function positive(value: unknown, field: string, optional = false): number | null {
  if (optional && (value === undefined || value === null || value === '')) return null
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) throw new HttpError(400, `${field} 格式无效`)
  return parsed
}

function serialize(row: ConditionalRow) {
  const numberString = (value: number | null) => value === null ? null : String(value)
  return {
    id: row.id,
    symbol: row.symbol,
    market: row.market,
    order_kind: row.order_kind,
    side: row.side,
    position_side: row.position_side,
    trigger_price: numberString(row.trigger_price),
    quantity: numberString(row.quantity),
    leverage: row.leverage,
    margin: numberString(row.margin),
    margin_mode: row.margin_mode,
    expires_at: row.expires_at ? new Date(row.expires_at).toISOString() : null,
    status: row.status,
    triggered_order_id: row.triggered_order_id,
    note: row.note,
    created_at: new Date(row.created_at).toISOString(),
    updated_at: new Date(row.updated_at).toISOString(),
  }
}

async function create(
  request: Request,
  env: Env,
  requestId: string,
  aiPlan = false,
) {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const market = String(body.market ?? '')
  if (!['cn', 'us', 'hk', 'crypto'].includes(market)) throw new HttpError(400, 'market 格式无效')
  const symbol = String(body.symbol ?? '').trim().toUpperCase()
  if (!symbol) throw new HttpError(400, 'symbol 格式无效')
  let orderKind = String(body.order_kind ?? 'limit')
  let side = String(body.side ?? 'buy')
  let positionSide = body.position_side === 'short' ? 'short' : 'long'
  let leverage = positive(body.leverage, 'leverage', true)
  let margin = positive(body.margin, 'margin', true)
  let quantity = positive(body.quantity, 'quantity', true)
  if (aiPlan) {
    orderKind = 'limit'
    const direction = String(body.direction ?? '')
    side = direction === 'open_short' ? 'sell' : 'buy'
    positionSide = direction === 'open_short' ? 'short' : 'long'
    if (market === 'crypto') {
      const preset = await env.DB.prepare(
        `SELECT perp_leverage, perp_notional_usdt, perp_margin_mode
         FROM bot_order_presets WHERE user_id = ?`,
      ).bind(user.id).first<{
        perp_leverage: number
        perp_notional_usdt: string
        perp_margin_mode: 'isolated' | 'cross'
      }>()
      leverage = preset?.perp_leverage ?? 3
      margin = Number(preset?.perp_notional_usdt ?? 100) / leverage
      body.margin_mode = preset?.perp_margin_mode ?? 'isolated'
    }
  }
  if (!['limit', 'stop_loss', 'take_profit'].includes(orderKind)) {
    throw new HttpError(400, 'order_kind 格式无效')
  }
  if (side !== 'buy' && side !== 'sell') throw new HttpError(400, 'side 格式无效')
  const triggerPrice = positive(body.trigger_price ?? body.entry_price, 'trigger_price')!
  if (market === 'crypto' && orderKind === 'limit' && margin !== null) {
    if (!leverage || leverage < 1 || leverage > 20) throw new HttpError(400, 'leverage 必须在 1 到 20 之间')
  } else if (quantity === null) {
    throw new HttpError(400, 'quantity 必填')
  }
  const expiresAt = typeof body.expires_at === 'string'
    ? new Date(body.expires_at).valueOf()
    : null
  if (expiresAt !== null && (!Number.isFinite(expiresAt) || expiresAt <= Date.now())) {
    throw new HttpError(400, 'expires_at 必须是未来时间')
  }
  const now = Date.now()
  const result = await env.DB.prepare(
    `INSERT INTO conditional_orders
      (user_id, symbol, market, order_kind, side, position_side,
       trigger_price, quantity, leverage, margin, margin_mode, expires_at,
       status, note, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)`,
  ).bind(
    user.id, symbol, market, orderKind, side, positionSide, triggerPrice,
    quantity, leverage, margin,
    body.margin_mode === 'cross' ? 'cross' : margin !== null ? 'isolated' : null,
    expiresAt,
    aiPlan ? 'AI decision plan' : null,
    now,
    now,
  ).run()
  const row = await env.DB.prepare(
    'SELECT * FROM conditional_orders WHERE id = ?',
  ).bind(result.meta.last_row_id).first<ConditionalRow>()
  return jsonResponse(serialize(row!), 201, requestId, request.method)
}

async function list(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const status = new URL(request.url).searchParams.get('status')
  const rows = await env.DB.prepare(
    `SELECT * FROM conditional_orders
     WHERE user_id = ? AND (? IS NULL OR status = ?)
     ORDER BY id DESC LIMIT 200`,
  ).bind(user.id, status, status).all<ConditionalRow>()
  return jsonResponse(rows.results.map(serialize), 200, requestId, request.method)
}

async function cancel(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  const { user } = await authenticate(request, env)
  const result = await env.DB.prepare(
    `UPDATE conditional_orders SET status = 'cancelled', updated_at = ?
     WHERE id = ? AND user_id = ? AND status = 'active'`,
  ).bind(Date.now(), id, user.id).run()
  if (result.meta.changes !== 1) throw new HttpError(404, '条件单不存在或不可撤销')
  return jsonResponse({}, 204, requestId, request.method)
}

function shouldTrigger(row: ConditionalRow, price: number): boolean {
  if (row.order_kind === 'limit') return row.side === 'buy'
    ? price <= row.trigger_price
    : price >= row.trigger_price
  if (row.order_kind === 'stop_loss') return row.position_side === 'long'
    ? price <= row.trigger_price
    : price >= row.trigger_price
  return row.position_side === 'long'
    ? price >= row.trigger_price
    : price <= row.trigger_price
}

export async function runConditionalOrderScan(env: Env): Promise<void> {
  const now = Date.now()
  await env.DB.prepare(
    `UPDATE conditional_orders SET status = 'expired', updated_at = ?
     WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= ?`,
  ).bind(now, now).run()
  const rows = await env.DB.prepare(
    `SELECT * FROM conditional_orders WHERE status = 'active' ORDER BY id LIMIT 50`,
  ).all<ConditionalRow>()
  const prices = new Map<string, Promise<number>>()
  for (const row of rows.results) {
    const key = `${row.market}|${row.symbol}`
    let pending = prices.get(key)
    if (!pending) {
      pending = fetchMarketKlines({
        symbol: row.symbol,
        market: row.market,
        period: '5m',
        instrument: row.market === 'crypto' && row.margin !== null ? 'perp' : 'spot',
        limit: 2,
      }).then((result) => {
        const price = result.items.at(-1)?.close
        if (!price) throw new Error('latest price unavailable')
        return price
      })
      prices.set(key, pending)
    }
    try {
      const price = await pending
      if (!shouldTrigger(row, price)) continue
      let order: Record<string, unknown>
      if (row.market === 'crypto' && row.order_kind === 'limit' && row.margin !== null) {
        order = await executePerpOrder(env, {
          userId: row.user_id,
          symbol: row.symbol,
          intent: row.position_side === 'short' ? 'open_short' : 'open_long',
          leverage: row.leverage ?? 1,
          margin: row.margin,
          marginMode: row.margin_mode ?? 'isolated',
        })
      } else {
        order = await executeSpotOrder(env, {
          userId: row.user_id,
          symbol: row.symbol,
          market: row.market,
          side: row.side,
          positionSide: row.position_side,
          quantity: row.quantity!,
          source: 'conditional',
        })
      }
      await env.DB.prepare(
        `UPDATE conditional_orders
         SET status = 'triggered', triggered_order_id = ?, updated_at = ?
         WHERE id = ? AND status = 'active'`,
      ).bind(Number(order.id ?? 0), now, row.id).run()
    } catch (cause) {
      await env.DB.prepare(
        `UPDATE conditional_orders SET status = 'failed', note = ?, updated_at = ?
         WHERE id = ? AND status = 'active'`,
      ).bind(
        (cause instanceof Error ? cause.message : String(cause)).slice(0, 128),
        now,
        row.id,
      ).run()
    }
  }
}

export async function handleConditionalOrderRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (path === '/api/v1/virtual/conditional-orders') {
    if (request.method === 'GET') return list(request, env, requestId)
    if (request.method === 'POST') return create(request, env, requestId)
  }
  if (path === '/api/v1/virtual/ai-plan-order' && request.method === 'POST') {
    return create(request, env, requestId, true)
  }
  const match = path.match(/^\/api\/v1\/virtual\/conditional-orders\/(\d+)$/u)
  if (match?.[1] && request.method === 'DELETE') {
    return cancel(request, env, requestId, Number(match[1]))
  }
  return path.startsWith('/api/v1/virtual/conditional-orders') ||
    path === '/api/v1/virtual/ai-plan-order'
    ? jsonResponse({ detail: 'Route not found' }, 404, requestId, request.method)
    : null
}
