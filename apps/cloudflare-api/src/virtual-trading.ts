import { authenticate } from './auth'
import { HttpError, jsonResponse, readJsonObject } from './http'
import { fetchMarketKlines } from './market'

const MARKETS = new Set(['cn', 'us', 'hk', 'crypto'])
const CURRENCIES: Readonly<Record<string, string>> = {
  cn: 'CNY',
  us: 'USD',
  hk: 'HKD',
  crypto: 'USDT',
}
const COMMISSION_RATE = 0.001
const SLIPPAGE_RATE = 0.001
const PERP_FEE_RATE = 0.0005
const PERP_MMR = 0.005

type AccountRow = Readonly<{
  id: number
  user_id: string
  market: string
  currency: string
  initial_capital: number
  cash_balance: number
  realized_pnl: number
  activated_at: number
}>

type PositionRow = Readonly<{
  id: number
  account_id: number
  symbol: string
  market: string
  position_side: 'long' | 'short'
  quantity: number
  avg_entry_price: number
  realized_pnl: number
  opened_at: number
  closed_at: number | null
}>

type PerpPositionRow = Readonly<{
  id: number
  account_id: number
  symbol: string
  side: 'long' | 'short'
  margin_mode: 'isolated' | 'cross'
  leverage: number
  quantity: number
  entry_price: number
  initial_margin: number
  maintenance_margin_rate: number
  liquidation_price: number
  realized_pnl: number
  fee_paid: number
  funding_paid: number
  opened_at: number
  closed_at: number | null
  close_reason: 'manual' | 'liquidated' | 'reset' | null
}>

function finiteNumber(value: unknown, field: string, min = 0): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= min) {
    throw new HttpError(400, `${field} 必须大于 ${min}`)
  }
  return parsed
}

function decimal(value: number | null): string | null {
  return value === null || !Number.isFinite(value)
    ? null
    : value.toFixed(8).replace(/\.?0+$/u, '') || '0'
}

function normalizeSymbol(value: unknown, market: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new HttpError(400, 'symbol 格式无效')
  }
  const symbol = value.trim().toUpperCase()
  if (market === 'crypto') {
    const base = symbol.replace(/[-_/]?(USDT|USD)$/u, '')
    return `${base}/USDT`
  }
  return symbol
}

async function latestPrice(
  symbol: string,
  market: string,
  instrument: 'spot' | 'perp' = 'spot',
): Promise<number> {
  const result = await fetchMarketKlines({
    symbol,
    market,
    period: '5m',
    instrument,
    limit: 2,
  })
  const price = result.items.at(-1)?.close
  if (!price || price <= 0) throw new HttpError(503, '最新行情暂不可用')
  return price
}

function serializeAccount(row: AccountRow) {
  return {
    id: row.id,
    market: row.market,
    currency: row.currency,
    initial_capital: decimal(row.initial_capital),
    cash_balance: decimal(row.cash_balance),
    realized_pnl: decimal(row.realized_pnl),
    activated_at: new Date(row.activated_at).toISOString(),
  }
}

function serializePosition(row: PositionRow) {
  return {
    id: row.id,
    symbol: row.symbol,
    market: row.market,
    position_side: row.position_side,
    quantity: decimal(row.quantity),
    avg_entry_price: decimal(row.avg_entry_price),
    realized_pnl: decimal(row.realized_pnl),
    opened_at: new Date(row.opened_at).toISOString(),
    closed_at: row.closed_at ? new Date(row.closed_at).toISOString() : null,
  }
}

async function writeEquitySnapshot(
  env: Env,
  accountId: number,
  triggerKind: 'order_filled' | 'daily' | 'migration',
): Promise<void> {
  const account = await env.DB.prepare('SELECT * FROM virtual_accounts WHERE id = ?')
    .bind(accountId).first<AccountRow>()
  if (!account) return
  const [spot, perps] = await Promise.all([
    env.DB.prepare(
      'SELECT * FROM virtual_positions WHERE account_id = ? AND closed_at IS NULL',
    ).bind(accountId).all<PositionRow>(),
    env.DB.prepare(
      'SELECT * FROM virtual_perp_positions WHERE account_id = ? AND closed_at IS NULL',
    ).bind(accountId).all<PerpPositionRow>(),
  ])
  let positionsValue = 0
  for (const position of spot.results) {
    let mark = position.avg_entry_price
    try { mark = await latestPrice(position.symbol, position.market) } catch { /* fallback */ }
    positionsValue += (position.position_side === 'short' ? -1 : 1) * mark * position.quantity
  }
  for (const position of perps.results) {
    let mark = position.entry_price
    try { mark = await latestPrice(position.symbol, 'crypto', 'perp') } catch { /* fallback */ }
    const unrealized = position.side === 'long'
      ? (mark - position.entry_price) * position.quantity
      : (position.entry_price - mark) * position.quantity
    positionsValue += position.initial_margin + unrealized
  }
  await env.DB.prepare(
    `INSERT INTO virtual_equity_snapshots
      (account_id, market, cash, positions_value, equity,
       realized_pnl_cumulative, trigger_kind, snapshot_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    account.id, account.market, account.cash_balance, positionsValue,
    account.cash_balance + positionsValue, account.realized_pnl,
    triggerKind, Date.now(),
  ).run()
}

async function ownedAccount(
  env: Env,
  userId: string,
  market: string,
): Promise<AccountRow> {
  const row = await env.DB
    .prepare('SELECT * FROM virtual_accounts WHERE user_id = ? AND market = ?')
    .bind(userId, market)
    .first<AccountRow>()
  if (!row) throw new HttpError(404, '请先激活对应市场的模拟账户')
  return row
}

async function listAccounts(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const rows = await env.DB
    .prepare('SELECT * FROM virtual_accounts WHERE user_id = ? ORDER BY id')
    .bind(user.id)
    .all<AccountRow>()
  return jsonResponse(rows.results.map(serializeAccount), 200, requestId, request.method)
}

async function accountByMarket(
  request: Request,
  env: Env,
  requestId: string,
  market: string,
) {
  const { user } = await authenticate(request, env)
  const row = await env.DB
    .prepare('SELECT * FROM virtual_accounts WHERE user_id = ? AND market = ?')
    .bind(user.id, market)
    .first<AccountRow>()
  if (!row) throw new HttpError(404, '模拟账户尚未激活')
  return jsonResponse(serializeAccount(row), 200, requestId, request.method)
}

async function resetAccount(
  request: Request,
  env: Env,
  requestId: string,
  market: string,
) {
  if (!MARKETS.has(market)) throw new HttpError(400, 'market 不受支持')
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const initialCapital = finiteNumber(body.initial_capital, 'initial_capital', 99)
  const now = Date.now()
  await env.DB
    .prepare('DELETE FROM virtual_accounts WHERE user_id = ? AND market = ?')
    .bind(user.id, market)
    .run()
  const created = await env.DB
    .prepare(
      `INSERT INTO virtual_accounts
        (user_id, market, currency, initial_capital, cash_balance,
         realized_pnl, activated_at, updated_at)
       VALUES (?, ?, ?, ?, ?, 0, ?, ?)`,
    )
    .bind(user.id, market, CURRENCIES[market], initialCapital, initialCapital, now, now)
    .run()
  const row = await env.DB
    .prepare('SELECT * FROM virtual_accounts WHERE id = ?')
    .bind(created.meta.last_row_id)
    .first<AccountRow>()
  await writeEquitySnapshot(env, Number(created.meta.last_row_id), 'migration')
  return jsonResponse(serializeAccount(row!), 200, requestId, request.method)
}

export async function executeSpotOrder(
  env: Env,
  input: Readonly<{
    userId: string
    symbol: string
    market: string
    side: 'buy' | 'sell'
    positionSide: 'long' | 'short'
    quantity: number
    source?: string
  }>,
): Promise<Record<string, unknown>> {
  if (!MARKETS.has(input.market)) throw new HttpError(400, 'market 不受支持')
  if (input.positionSide === 'short' && input.market !== 'us') {
    throw new HttpError(400, '当前仅美股模拟账户支持卖空')
  }
  const account = await ownedAccount(env, input.userId, input.market)
  const symbol = normalizeSymbol(input.symbol, input.market)
  const mark = await latestPrice(symbol, input.market)
  const isBuyExecution =
    (input.positionSide === 'long' && input.side === 'buy') ||
    (input.positionSide === 'short' && input.side === 'buy')
  const fill = mark * (isBuyExecution ? 1 + SLIPPAGE_RATE : 1 - SLIPPAGE_RATE)
  const quantity = input.quantity
  const notional = fill * quantity
  const commission = notional * COMMISSION_RATE
  const now = Date.now()
  const position = await env.DB
    .prepare(
      `SELECT * FROM virtual_positions
       WHERE account_id = ? AND symbol = ? AND position_side = ? AND closed_at IS NULL`,
    )
    .bind(account.id, symbol, input.positionSide)
    .first<PositionRow>()

  const opens =
    (input.positionSide === 'long' && input.side === 'buy') ||
    (input.positionSide === 'short' && input.side === 'sell')
  let realized = 0
  let cashDelta = 0
  const statements: D1PreparedStatement[] = []
  if (opens) {
    const required = notional + commission
    if (account.cash_balance + 1e-8 < required) throw new HttpError(400, '模拟账户可用资金不足')
    cashDelta = input.positionSide === 'short' ? notional - commission : -required
    if (position) {
      const nextQuantity = position.quantity + quantity
      const nextAverage =
        (position.quantity * position.avg_entry_price + notional) / nextQuantity
      statements.push(
        env.DB.prepare(
          `UPDATE virtual_positions
           SET quantity = ?, avg_entry_price = ? WHERE id = ?`,
        ).bind(nextQuantity, nextAverage, position.id),
      )
    } else {
      statements.push(
        env.DB.prepare(
          `INSERT INTO virtual_positions
            (account_id, symbol, market, position_side, quantity,
             avg_entry_price, realized_pnl, opened_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?)`,
        ).bind(account.id, symbol, input.market, input.positionSide, quantity, fill, now),
      )
    }
  } else {
    if (!position || position.quantity + 1e-8 < quantity) {
      throw new HttpError(400, '可平仓数量不足')
    }
    realized = input.positionSide === 'long'
      ? (fill - position.avg_entry_price) * quantity - commission
      : (position.avg_entry_price - fill) * quantity - commission
    cashDelta = input.positionSide === 'short' ? -notional - commission : notional - commission
    const remaining = position.quantity - quantity
    statements.push(
      env.DB.prepare(
        `UPDATE virtual_positions
         SET quantity = ?, realized_pnl = realized_pnl + ?, closed_at = ?
         WHERE id = ?`,
      ).bind(remaining, realized, remaining <= 1e-8 ? now : null, position.id),
    )
  }
  statements.push(
    env.DB.prepare(
      `UPDATE virtual_accounts
       SET cash_balance = cash_balance + ?, realized_pnl = realized_pnl + ?, updated_at = ?
       WHERE id = ?`,
    ).bind(cashDelta, realized, now, account.id),
    env.DB.prepare(
      `INSERT INTO virtual_orders
        (account_id, symbol, market, side, position_side, order_type,
         quantity, price, notional, commission, slippage_cost, realized_pnl,
         status, source, placed_at, filled_at)
       VALUES (?, ?, ?, ?, ?, 'market', ?, ?, ?, ?, ?, ?, 'filled', ?, ?, ?)`,
    ).bind(
      account.id,
      symbol,
      input.market,
      input.side,
      input.positionSide,
      quantity,
      fill,
      notional,
      commission,
      Math.abs(fill - mark) * quantity,
      realized,
      input.source ?? 'manual',
      now,
      now,
    ),
  )
  const results = await env.DB.batch(statements)
  const orderId = Number(results.at(-1)?.meta.last_row_id)
  await writeEquitySnapshot(env, account.id, 'order_filled')
  return {
    id: orderId,
    account_id: account.id,
    symbol,
    market: input.market,
    side: input.side,
    position_side: input.positionSide,
    order_type: 'market',
    quantity: decimal(quantity),
    price: decimal(fill),
    notional: decimal(notional),
    commission: decimal(commission),
    slippage_cost: decimal(Math.abs(fill - mark) * quantity),
    realized_pnl: decimal(realized),
    status: 'filled',
    reject_reason: null,
    placed_at: new Date(now).toISOString(),
    filled_at: new Date(now).toISOString(),
  }
}

async function placeSpotOrder(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const market = String(body.market ?? '')
  const side = body.side === 'sell' ? 'sell' : body.side === 'buy' ? 'buy' : null
  const positionSide = body.position_side === 'short' ? 'short' : 'long'
  if (!side) throw new HttpError(400, 'side 格式无效')
  const result = await executeSpotOrder(env, {
    userId: user.id,
    symbol: String(body.symbol ?? ''),
    market,
    side,
    positionSide,
    quantity: finiteNumber(body.quantity, 'quantity'),
  })
  return jsonResponse(result, 200, requestId, request.method)
}

function serializeOrder(row: Record<string, unknown>) {
  const numericFields = [
    'quantity', 'price', 'notional', 'commission', 'slippage_cost', 'realized_pnl',
  ]
  const result = { ...row }
  for (const field of numericFields) {
    const value = result[field]
    result[field] = value === null || value === undefined ? null : decimal(Number(value))
  }
  for (const field of ['placed_at', 'filled_at']) {
    const value = result[field]
    result[field] = typeof value === 'number' ? new Date(value).toISOString() : null
  }
  return result
}

async function listOrders(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const url = new URL(request.url)
  const market = url.searchParams.get('market')
  const limit = Math.min(Math.max(Number(url.searchParams.get('limit') ?? 50), 1), 200)
  const beforeId = Number(url.searchParams.get('before_id') ?? 0)
  const rows = await env.DB.prepare(
    `SELECT o.* FROM virtual_orders o
     JOIN virtual_accounts a ON a.id = o.account_id
     WHERE a.user_id = ?
       AND (? IS NULL OR o.market = ?)
       AND (? = 0 OR o.id < ?)
     ORDER BY o.id DESC LIMIT ?`,
  ).bind(user.id, market, market, beforeId, beforeId, limit).all<Record<string, unknown>>()
  return jsonResponse(rows.results.map(serializeOrder), 200, requestId, request.method)
}

async function listPositions(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const url = new URL(request.url)
  const market = url.searchParams.get('market')
  const includeClosed = url.searchParams.get('include_closed') === 'true'
  const rows = await env.DB.prepare(
    `SELECT p.* FROM virtual_positions p
     JOIN virtual_accounts a ON a.id = p.account_id
     WHERE a.user_id = ?
       AND (? IS NULL OR p.market = ?)
       AND (? = 1 OR p.closed_at IS NULL)
     ORDER BY p.id DESC`,
  ).bind(user.id, market, market, includeClosed ? 1 : 0).all<PositionRow>()
  return jsonResponse(rows.results.map(serializePosition), 200, requestId, request.method)
}

async function portfolio(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const accounts = await env.DB.prepare(
    'SELECT * FROM virtual_accounts WHERE user_id = ? ORDER BY id',
  ).bind(user.id).all<AccountRow>()
  const summaries = []
  for (const account of accounts.results) {
    const positions = await env.DB.prepare(
      `SELECT * FROM virtual_positions WHERE account_id = ? AND closed_at IS NULL`,
    ).bind(account.id).all<PositionRow>()
    const views = []
    let positionsValue = 0
    for (const position of positions.results) {
      let current: number | null = null
      try {
        current = await latestPrice(position.symbol, position.market)
      } catch {
        current = position.avg_entry_price
      }
      const value = current * position.quantity
      const unrealized = position.position_side === 'long'
        ? (current - position.avg_entry_price) * position.quantity
        : (position.avg_entry_price - current) * position.quantity
      positionsValue += position.position_side === 'short' ? -value : value
      views.push({
        id: position.id,
        symbol: position.symbol,
        market: position.market,
        position_side: position.position_side,
        quantity: decimal(position.quantity),
        avg_entry_price: decimal(position.avg_entry_price),
        current_price: decimal(current),
        unrealized_pnl: decimal(unrealized),
        value: decimal(value),
      })
    }
    const perps = await env.DB.prepare(
      'SELECT * FROM virtual_perp_positions WHERE account_id = ? AND closed_at IS NULL',
    ).bind(account.id).all<PerpPositionRow>()
    const perpViews = []
    for (const position of perps.results) {
      let mark = position.entry_price
      try { mark = await latestPrice(position.symbol, 'crypto', 'perp') } catch { /* fallback */ }
      const view = serializePerpPosition(position, mark)
      positionsValue += position.initial_margin + Number(view.unrealized_pnl ?? 0)
      perpViews.push(view)
    }
    summaries.push({
      account_id: account.id,
      market: account.market,
      currency: account.currency,
      initial_capital: decimal(account.initial_capital),
      cash_balance: decimal(account.cash_balance),
      realized_pnl: decimal(account.realized_pnl),
      positions: views,
      perp_positions: perpViews,
      positions_value: decimal(positionsValue),
      total_equity: decimal(account.cash_balance + positionsValue),
    })
  }
  return jsonResponse(summaries, 200, requestId, request.method)
}

async function aiOrder(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const market = String(body.market ?? '')
  const direction = String(body.direction ?? '')
  const symbol = normalizeSymbol(body.symbol, market)
  if (!MARKETS.has(market)) throw new HttpError(400, 'market 不受支持')
  const account = await ownedAccount(env, user.id, market)
  if (market === 'crypto') {
    if (direction !== 'open_long' && direction !== 'open_short') {
      throw new HttpError(400, '加密 AI 模拟下单仅支持 open_long/open_short')
    }
    const margin = Math.max(account.cash_balance * 0.05, 10)
    await executePerpOrder(env, {
      userId: user.id,
      symbol,
      intent: direction,
      leverage: 3,
      margin: Math.min(margin, account.cash_balance * 0.9),
      marginMode: 'isolated',
    })
  } else {
    if (direction !== 'buy' && direction !== 'sell') {
      throw new HttpError(400, '现货 AI 模拟下单仅支持 buy/sell')
    }
    let quantity: number
    if (direction === 'sell') {
      const position = await env.DB.prepare(
        `SELECT quantity FROM virtual_positions
         WHERE account_id = ? AND symbol = ? AND position_side = 'long'
           AND closed_at IS NULL`,
      ).bind(account.id, symbol).first<{ quantity: number }>()
      if (!position) throw new HttpError(409, '当前没有可供 AI 平仓的模拟持仓')
      quantity = position.quantity
    } else {
      const price = await latestPrice(symbol, market)
      quantity = Math.max((account.cash_balance * 0.05) / price, market === 'cn' ? 100 : 0.000001)
      if (market === 'cn') quantity = Math.max(Math.floor(quantity / 100) * 100, 100)
    }
    await executeSpotOrder(env, {
      userId: user.id,
      symbol,
      market,
      side: direction,
      positionSide: 'long',
      quantity,
      source: 'ai_signal',
    })
  }
  return jsonResponse({
    filled: true,
    title: 'AI 模拟订单已成交',
    detail: '订单已进入独立模拟账户，可在持仓与订单中查看。',
    source: 'ai_signal',
  }, 200, requestId, request.method)
}

async function equityCurves(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const days = Math.min(Math.max(Number(new URL(request.url).searchParams.get('days') ?? 30), 1), 365)
  const since = Date.now() - days * 86_400_000
  const rows = await env.DB.prepare(
    `SELECT s.*, a.market FROM virtual_equity_snapshots s
     JOIN virtual_accounts a ON a.id = s.account_id
     WHERE a.user_id = ? AND s.snapshot_at >= ?
     ORDER BY s.snapshot_at`,
  ).bind(user.id, since).all<Record<string, unknown>>()
  const curves: Record<string, unknown[]> = {}
  for (const row of rows.results) {
    const market = String(row.market)
    const points = curves[market] ?? []
    points.push({
      cash: decimal(Number(row.cash)),
      positions_value: decimal(Number(row.positions_value)),
      equity: decimal(Number(row.equity)),
      realized_pnl_cumulative: decimal(Number(row.realized_pnl_cumulative)),
      snapshot_at: new Date(Number(row.snapshot_at)).toISOString(),
    })
    curves[market] = points
  }
  return jsonResponse({ curves }, 200, requestId, request.method)
}

function serializePerpPosition(row: PerpPositionRow, mark: number) {
  const unrealized = row.side === 'long'
    ? (mark - row.entry_price) * row.quantity
    : (row.entry_price - mark) * row.quantity
  const distance = Math.abs(mark - row.liquidation_price) / mark * 100
  return {
    id: row.id,
    symbol: row.symbol,
    side: row.side,
    leverage: row.leverage,
    margin_mode: row.margin_mode,
    quantity: decimal(row.quantity),
    entry_price: decimal(row.entry_price),
    initial_margin: decimal(row.initial_margin),
    liquidation_price: decimal(row.liquidation_price),
    realized_pnl: decimal(row.realized_pnl),
    fee_paid: decimal(row.fee_paid),
    funding_paid: decimal(row.funding_paid),
    opened_at: new Date(row.opened_at).toISOString(),
    closed_at: row.closed_at ? new Date(row.closed_at).toISOString() : null,
    close_reason: row.close_reason,
    mark_price: decimal(mark),
    unrealized_pnl: decimal(unrealized),
    liquidation_distance_pct: decimal(distance),
    roe_pct: decimal((unrealized / row.initial_margin) * 100),
  }
}

export async function executePerpOrder(
  env: Env,
  input: Readonly<{
    userId: string
    symbol: string
    intent: 'open_long' | 'open_short' | 'close'
    leverage?: number
    margin?: number
    quantity?: number
    closeAll?: boolean
    marginMode?: 'isolated' | 'cross'
    closeReason?: 'manual' | 'liquidated'
    isLiquidation?: boolean
  }>,
): Promise<Record<string, unknown>> {
  const account = await ownedAccount(env, input.userId, 'crypto')
  const symbol = normalizeSymbol(input.symbol, 'crypto')
  const mark = await latestPrice(symbol, 'crypto', 'perp')
  const current = await env.DB.prepare(
    `SELECT * FROM virtual_perp_positions
     WHERE account_id = ? AND symbol = ? AND closed_at IS NULL`,
  ).bind(account.id, symbol).first<PerpPositionRow>()
  const now = Date.now()
  if (input.intent !== 'close') {
    if (current) throw new HttpError(409, '该合约已有活跃模拟持仓，请先平仓')
    const leverage = Math.trunc(input.leverage ?? 1)
    if (leverage < 1 || leverage > 20) throw new HttpError(400, 'leverage 必须在 1 到 20 之间')
    const side = input.intent === 'open_long' ? 'long' : 'short'
    const fill = mark * (side === 'long' ? 1 + SLIPPAGE_RATE : 1 - SLIPPAGE_RATE)
    const margin = input.margin ?? ((input.quantity ?? 0) * fill) / leverage
    if (!Number.isFinite(margin) || margin <= 0) throw new HttpError(400, 'margin 或 quantity 格式无效')
    const quantity = input.quantity ?? (margin * leverage) / fill
    const notional = quantity * fill
    const fee = notional * PERP_FEE_RATE
    if (account.cash_balance + 1e-8 < margin + fee) throw new HttpError(400, '模拟账户可用 USDT 不足')
    const liquidation = side === 'long'
      ? fill * (1 - 1 / leverage + PERP_MMR)
      : fill * (1 + 1 / leverage - PERP_MMR)
    const created = await env.DB.batch([
      env.DB.prepare(
        `UPDATE virtual_accounts SET cash_balance = cash_balance - ?, updated_at = ? WHERE id = ?`,
      ).bind(margin + fee, now, account.id),
      env.DB.prepare(
        `INSERT INTO virtual_perp_positions
          (account_id, symbol, side, margin_mode, leverage, quantity,
           entry_price, initial_margin, maintenance_margin_rate,
           liquidation_price, fee_paid, opened_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).bind(
        account.id, symbol, side, input.marginMode ?? 'isolated', leverage,
        quantity, fill, margin, PERP_MMR, Math.max(liquidation, 0), fee, now,
      ),
    ])
    const positionId = Number(created[1]?.meta.last_row_id)
    const order = await env.DB.prepare(
      `INSERT INTO virtual_perp_orders
        (account_id, position_id, symbol, action, leverage, quantity, price,
         notional, margin_delta, fee, realized_pnl, status, placed_at, filled_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'filled', ?, ?)`,
    ).bind(
      account.id, positionId, symbol, input.intent, leverage, quantity, fill,
      notional, margin, fee, now, now,
    ).run()
    await writeEquitySnapshot(env, account.id, 'order_filled')
    return {
      id: Number(order.meta.last_row_id), account_id: account.id, position_id: positionId,
      symbol, action: input.intent, leverage, quantity: decimal(quantity), price: decimal(fill),
      notional: decimal(notional), margin_delta: decimal(margin), fee: decimal(fee),
      realized_pnl: '0', status: 'filled', reject_reason: null, is_liquidation: false,
      placed_at: new Date(now).toISOString(), filled_at: new Date(now).toISOString(),
    }
  }
  if (!current) throw new HttpError(404, '未找到可平模拟持仓')
  const closeQuantity = input.closeAll === false && input.quantity
    ? Math.min(input.quantity, current.quantity)
    : current.quantity
  const fill = mark * (current.side === 'long' ? 1 - SLIPPAGE_RATE : 1 + SLIPPAGE_RATE)
  const pnl = current.side === 'long'
    ? (fill - current.entry_price) * closeQuantity
    : (current.entry_price - fill) * closeQuantity
  const notional = fill * closeQuantity
  const fee = notional * PERP_FEE_RATE
  const marginRelease = current.initial_margin * (closeQuantity / current.quantity)
  const remaining = current.quantity - closeQuantity
  const realized = pnl - fee
  const action = current.side === 'long' ? 'close_long' : 'close_short'
  const results = await env.DB.batch([
    env.DB.prepare(
      `UPDATE virtual_accounts
       SET cash_balance = cash_balance + ?, realized_pnl = realized_pnl + ?, updated_at = ?
       WHERE id = ?`,
    ).bind(marginRelease + realized, realized, now, account.id),
    env.DB.prepare(
      `UPDATE virtual_perp_positions
       SET quantity = ?, initial_margin = initial_margin - ?, realized_pnl = realized_pnl + ?,
           fee_paid = fee_paid + ?, closed_at = ?, close_reason = ?
       WHERE id = ?`,
    ).bind(
      remaining, marginRelease, realized, fee,
      remaining <= 1e-8 ? now : null,
      remaining <= 1e-8 ? (input.closeReason ?? 'manual') : null,
      current.id,
    ),
    env.DB.prepare(
      `INSERT INTO virtual_perp_orders
        (account_id, position_id, symbol, action, leverage, quantity, price,
         notional, margin_delta, fee, realized_pnl, status, is_liquidation,
         placed_at, filled_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'filled', ?, ?, ?)`,
    ).bind(
      account.id, current.id, symbol, action, current.leverage, closeQuantity,
      fill, notional, -marginRelease, fee, realized, input.isLiquidation ? 1 : 0, now, now,
    ),
  ])
  await writeEquitySnapshot(env, account.id, 'order_filled')
  return {
    id: Number(results[2]?.meta.last_row_id), account_id: account.id,
    position_id: current.id, symbol, action, leverage: current.leverage,
    quantity: decimal(closeQuantity), price: decimal(fill), notional: decimal(notional),
    margin_delta: decimal(-marginRelease), fee: decimal(fee), realized_pnl: decimal(realized),
    status: 'filled', reject_reason: null, is_liquidation: input.isLiquidation === true,
    placed_at: new Date(now).toISOString(), filled_at: new Date(now).toISOString(),
  }
}

async function placePerpOrder(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const intent = body.intent
  if (intent !== 'open_long' && intent !== 'open_short' && intent !== 'close') {
    throw new HttpError(400, 'intent 格式无效')
  }
  const result = await executePerpOrder(env, {
    userId: user.id,
    symbol: String(body.symbol ?? ''),
    intent,
    ...(body.leverage === undefined ? {} : { leverage: Number(body.leverage) }),
    ...(body.margin === undefined ? {} : { margin: Number(body.margin) }),
    ...(body.quantity === undefined ? {} : { quantity: Number(body.quantity) }),
    closeAll: body.close_all !== false,
    marginMode: body.margin_mode === 'cross' ? 'cross' : 'isolated',
  })
  return jsonResponse(result, 200, requestId, request.method)
}

async function listPerpPositions(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const includeClosed = new URL(request.url).searchParams.get('include_closed') === 'true'
  const rows = await env.DB.prepare(
    `SELECT p.* FROM virtual_perp_positions p
     JOIN virtual_accounts a ON a.id = p.account_id
     WHERE a.user_id = ? AND (? = 1 OR p.closed_at IS NULL)
     ORDER BY p.id DESC`,
  ).bind(user.id, includeClosed ? 1 : 0).all<PerpPositionRow>()
  const result = []
  for (const row of rows.results) {
    let mark = row.entry_price
    if (!row.closed_at) {
      try { mark = await latestPrice(row.symbol, 'crypto', 'perp') } catch { /* retain entry */ }
    }
    result.push(serializePerpPosition(row, mark))
  }
  return jsonResponse(result, 200, requestId, request.method)
}

async function listPerpOrders(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const url = new URL(request.url)
  const symbol = url.searchParams.get('symbol')
  const limit = Math.min(Math.max(Number(url.searchParams.get('limit') ?? 50), 1), 200)
  const beforeId = Number(url.searchParams.get('before_id') ?? 0)
  const rows = await env.DB.prepare(
    `SELECT o.* FROM virtual_perp_orders o
     JOIN virtual_accounts a ON a.id = o.account_id
     WHERE a.user_id = ? AND (? IS NULL OR o.symbol = ?)
       AND (? = 0 OR o.id < ?)
     ORDER BY o.id DESC LIMIT ?`,
  ).bind(user.id, symbol, symbol, beforeId, beforeId, limit).all<Record<string, unknown>>()
  return jsonResponse(rows.results.map((row) => ({
    ...serializeOrder(row),
    is_liquidation: row.is_liquidation === 1,
  })), 200, requestId, request.method)
}

async function listPerpFunding(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const url = new URL(request.url)
  const symbol = url.searchParams.get('symbol')
  const limit = Math.min(Math.max(Number(url.searchParams.get('limit') ?? 50), 1), 200)
  const rows = await env.DB.prepare(
    `SELECT f.* FROM virtual_perp_funding f
     JOIN virtual_accounts a ON a.id = f.account_id
     WHERE a.user_id = ? AND (? IS NULL OR f.symbol = ?)
     ORDER BY f.id DESC LIMIT ?`,
  ).bind(user.id, symbol, symbol, limit).all<Record<string, unknown>>()
  return jsonResponse(rows.results.map((row) => ({
    ...row,
    funding_rate: decimal(Number(row.funding_rate)),
    mark_price: decimal(Number(row.mark_price)),
    quantity: decimal(Number(row.quantity)),
    payment: decimal(Number(row.payment)),
    funding_ts: new Date(Number(row.funding_ts)).toISOString(),
    settled_at: new Date(Number(row.settled_at)).toISOString(),
  })), 200, requestId, request.method)
}

async function currentFundingRate(symbol: string): Promise<number> {
  const base = symbol.replace(/[-_/]?(USDT|USD)$/u, '')
  const url = new URL('https://www.okx.com/api/v5/public/funding-rate')
  url.searchParams.set('instId', `${base}-USDT-SWAP`)
  const response = await fetch(url, {
    headers: { accept: 'application/json', 'user-agent': 'Midas-Trading-Cloudflare/1.0' },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) throw new Error(`OKX funding HTTP ${response.status}`)
  const payload = await response.json() as { data?: Array<{ fundingRate?: string }> }
  const rate = Number(payload.data?.[0]?.fundingRate)
  if (!Number.isFinite(rate)) throw new Error('OKX funding payload incomplete')
  return rate
}

export async function runVirtualFundingSettlement(
  env: Env,
  scheduledTime = Date.now(),
): Promise<void> {
  const date = new Date(scheduledTime)
  // Run fifteen minutes after the exchange funding boundary. This avoids the
  // social-publishing cron slots while keeping the settlement period exact.
  if (date.getUTCMinutes() !== 15 || date.getUTCHours() % 8 !== 0) return
  const fundingTs = Date.UTC(
    date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), date.getUTCHours(),
  )
  const rows = await env.DB.prepare(
    'SELECT * FROM virtual_perp_positions WHERE closed_at IS NULL ORDER BY id LIMIT 100',
  ).all<PerpPositionRow>()
  const rateCache = new Map<string, Promise<number>>()
  for (const row of rows.results) {
    try {
      const exists = await env.DB.prepare(
        'SELECT 1 AS ok FROM virtual_perp_funding WHERE position_id = ? AND funding_ts = ?',
      ).bind(row.id, fundingTs).first<{ ok: number }>()
      if (exists) continue
      let pending = rateCache.get(row.symbol)
      if (!pending) {
        pending = currentFundingRate(row.symbol)
        rateCache.set(row.symbol, pending)
      }
      const [rate, mark] = await Promise.all([
        pending,
        latestPrice(row.symbol, 'crypto', 'perp'),
      ])
      // Positive payment means the position paid funding; negative means received.
      const payment = mark * row.quantity * rate * (row.side === 'long' ? 1 : -1)
      const now = Date.now()
      const inserted = await env.DB.prepare(
        `INSERT OR IGNORE INTO virtual_perp_funding
          (account_id, position_id, symbol, side, funding_rate, mark_price,
           quantity, payment, funding_ts, settled_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).bind(
        row.account_id, row.id, row.symbol, row.side, rate, mark,
        row.quantity, payment, fundingTs, now,
      ).run()
      if (inserted.meta.changes !== 1) continue
      await env.DB.batch([
        env.DB.prepare(
          'UPDATE virtual_accounts SET cash_balance = cash_balance - ?, updated_at = ? WHERE id = ?',
        ).bind(payment, now, row.account_id),
        env.DB.prepare(
          'UPDATE virtual_perp_positions SET funding_paid = funding_paid + ? WHERE id = ?',
        ).bind(payment, row.id),
      ])
      await writeEquitySnapshot(env, row.account_id, 'daily')
    } catch (cause) {
      console.error(JSON.stringify({
        event: 'virtual.funding_settlement_failed',
        positionId: row.id,
        error: cause instanceof Error ? cause.message : String(cause),
      }))
    }
  }
}

export async function runVirtualRiskScan(env: Env): Promise<void> {
  const rows = await env.DB.prepare(
    `SELECT * FROM virtual_perp_positions WHERE closed_at IS NULL ORDER BY id LIMIT 50`,
  ).all<PerpPositionRow>()
  for (const row of rows.results) {
    try {
      const mark = await latestPrice(row.symbol, 'crypto', 'perp')
      const liquidated = row.side === 'long'
        ? mark <= row.liquidation_price
        : mark >= row.liquidation_price
      if (!liquidated) continue
      const account = await env.DB.prepare(
        'SELECT user_id FROM virtual_accounts WHERE id = ?',
      ).bind(row.account_id).first<{ user_id: string }>()
      if (!account) continue
      await executePerpOrder(env, {
        userId: account.user_id,
        symbol: row.symbol,
        intent: 'close',
        closeAll: true,
        closeReason: 'liquidated',
        isLiquidation: true,
      })
    } catch (cause) {
      console.error(JSON.stringify({
        event: 'virtual.liquidation_scan_failed',
        positionId: row.id,
        error: cause instanceof Error ? cause.message : String(cause),
      }))
    }
  }
}

export async function handleVirtualTradingRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (!path.startsWith('/api/v1/virtual/')) return null
  if (path === '/api/v1/virtual/accounts' && request.method === 'GET') {
    return listAccounts(request, env, requestId)
  }
  const accountMatch = path.match(/^\/api\/v1\/virtual\/accounts\/(cn|us|hk|crypto)$/u)
  if (accountMatch?.[1]) {
    if (request.method === 'GET') return accountByMarket(request, env, requestId, accountMatch[1])
    if (request.method === 'PUT') return resetAccount(request, env, requestId, accountMatch[1])
  }
  if (path === '/api/v1/virtual/portfolio' && request.method === 'GET') {
    return portfolio(request, env, requestId)
  }
  if (path === '/api/v1/virtual/ai-order' && request.method === 'POST') {
    return aiOrder(request, env, requestId)
  }
  if (path === '/api/v1/virtual/orders') {
    if (request.method === 'GET') return listOrders(request, env, requestId)
    if (request.method === 'POST') return placeSpotOrder(request, env, requestId)
  }
  if (path === '/api/v1/virtual/positions' && request.method === 'GET') {
    return listPositions(request, env, requestId)
  }
  if (path === '/api/v1/virtual/equity-curves' && request.method === 'GET') {
    return equityCurves(request, env, requestId)
  }
  if (path === '/api/v1/virtual/hk-board-lot' && request.method === 'GET') {
    const symbol = new URL(request.url).searchParams.get('symbol') ?? ''
    const lots: Readonly<Record<string, number>> = {
      '00700': 100, '09988': 100, '03690': 100, '01810': 200,
      '00941': 500, '01211': 500,
    }
    const boardLot = lots[symbol.padStart(5, '0')]
    if (!boardLot) throw new HttpError(404, '暂无该港股每手股数')
    return jsonResponse({ symbol, board_lot: boardLot }, 200, requestId, request.method)
  }
  if (path === '/api/v1/virtual/perp/orders') {
    if (request.method === 'GET') return listPerpOrders(request, env, requestId)
    if (request.method === 'POST') return placePerpOrder(request, env, requestId)
  }
  if (path === '/api/v1/virtual/perp/positions' && request.method === 'GET') {
    return listPerpPositions(request, env, requestId)
  }
  if (path === '/api/v1/virtual/perp/funding' && request.method === 'GET') {
    return listPerpFunding(request, env, requestId)
  }
  return jsonResponse({ detail: 'Route not found' }, 404, requestId, request.method)
}
