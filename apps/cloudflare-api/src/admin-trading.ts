import {
  adminActionStatement,
  integerParam,
  requireAdmin,
} from './admin'
import { HttpError, jsonResponse, readJsonObject } from './http'
import {
  DEFAULT_STRATEGY_PARAMS as DEFAULT_PARAMS,
  normalizeStrategyParams,
  scoreQuote,
} from './strategy-score'

type Strategy = 'managed' | 'intelligent'

type AccountRow = Readonly<{
  strategy: Strategy
  enabled: number
  initial_capital: number
  cash_balance: number
  open_margin: number
  open_leverage: number
  max_positions: number
  allow_long: number
  allow_short: number
  exit_tp: number
  exit_signal: number
  exit_timeout: number
  tp_pct: number
  strategy_params_json: string
  updated_at: number
}>

type PositionRow = Readonly<{
  id: number
  strategy: Strategy
  symbol: string
  side: 'long' | 'short'
  leverage: number
  entry_price: number
  quantity: number
  margin: number
  mark_price: number
  stop_price: number | null
  tp_price: number | null
  signal_json: string
  opened_at: number
}>

type TradeRow = Readonly<{
  id: number
  strategy: Strategy
  symbol: string
  side: 'long' | 'short'
  leverage: number
  entry_price: number
  exit_price: number
  quantity: number
  margin: number
  pnl_usdt: number
  pnl_pct: number
  close_reason: string
  opened_at: number
  closed_at: number
}>

function iso(timestamp: number): string {
  return new Date(timestamp).toISOString()
}

function pnl(position: PositionRow, mark = position.mark_price): number {
  const direction = position.side === 'long' ? 1 : -1
  return (mark - position.entry_price) * position.quantity * direction
}

function parseObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value) as unknown
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {}
  } catch {
    return {}
  }
}

async function account(env: Env, strategy: Strategy): Promise<AccountRow> {
  const row = await env.DB
    .prepare('SELECT * FROM virtual_strategy_accounts WHERE strategy = ?')
    .bind(strategy)
    .first<AccountRow>()
  if (!row) throw new HttpError(500, '虚拟策略账户不存在')
  return row
}

async function positions(
  env: Env,
  strategy: Strategy,
): Promise<PositionRow[]> {
  const result = await env.DB
    .prepare(
      `SELECT * FROM virtual_strategy_positions
       WHERE strategy = ? ORDER BY opened_at DESC`,
    )
    .bind(strategy)
    .all<PositionRow>()
  return result.results
}

async function statusPayload(env: Env, strategy: Strategy) {
  const [state, openPositions] = await Promise.all([
    account(env, strategy),
    positions(env, strategy),
  ])
  const unrealized = openPositions.reduce((sum, item) => sum + pnl(item), 0)
  const occupiedMargin = openPositions.reduce(
    (sum, item) => sum + item.margin,
    0,
  )
  const accountValue = state.cash_balance + unrealized
  const common = {
    enabled: state.enabled === 1,
    account_ready: true,
    account_value: accountValue,
    cash_balance: state.cash_balance,
    initial_capital: state.initial_capital,
    open_positions: openPositions.length,
    open_margin: state.open_margin,
    open_leverage: state.open_leverage,
    max_positions: state.max_positions,
    allow_long: state.allow_long === 1,
  }
  if (strategy === 'managed') {
    return {
      ...common,
      available_funds: accountValue - occupiedMargin,
      occupied_margin: occupiedMargin,
      exit_tp: state.exit_tp === 1,
      exit_signal: state.exit_signal === 1,
      exit_timeout: state.exit_timeout === 1,
      tp_pct: state.tp_pct,
    }
  }
  return { ...common, allow_short: state.allow_short === 1 }
}

async function getStatus(
  request: Request,
  env: Env,
  requestId: string,
  strategy: Strategy,
): Promise<Response> {
  await requireAdmin(request, env)
  return jsonResponse(
    await statusPayload(env, strategy),
    200,
    requestId,
    request.method,
  )
}

async function listPositions(
  request: Request,
  env: Env,
  requestId: string,
  strategy: Strategy,
): Promise<Response> {
  await requireAdmin(request, env)
  const url = new URL(request.url)
  const offset = integerParam(url, 'offset', 0, 0, 1_000_000)
  const limit = integerParam(url, 'limit', 100, 1, 200)
  const [rows, total] = await Promise.all([
    env.DB
      .prepare(
        `SELECT * FROM virtual_strategy_positions
         WHERE strategy = ?
         ORDER BY opened_at DESC
         LIMIT ? OFFSET ?`,
      )
      .bind(strategy, limit, offset)
      .all<PositionRow>(),
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count FROM virtual_strategy_positions
         WHERE strategy = ?`,
      )
      .bind(strategy)
      .first<{ count: number }>(),
  ])
  return jsonResponse(
    {
      items: rows.results.map((row) => {
        const unrealized = pnl(row)
        const base = {
          id: row.id,
          symbol: row.symbol,
          leverage: row.leverage,
          entry_price: row.entry_price,
          quantity: row.quantity,
          margin: row.margin,
          opened_at: iso(row.opened_at),
          mark: row.mark_price,
          unrealized_pnl: unrealized,
          unrealized_pct: row.margin > 0 ? unrealized / row.margin * 100 : 0,
        }
        if (strategy === 'managed') {
          const signal = parseObject(row.signal_json)
          return { ...base, bias: String(signal.bias ?? '中性') }
        }
        return {
          ...base,
          side: row.side,
          stop_price: row.stop_price,
          tp_price: row.tp_price,
          signals: parseObject(row.signal_json),
        }
      }),
      total: Number(total?.count ?? 0),
    },
    200,
    requestId,
    request.method,
  )
}

async function listHistory(
  request: Request,
  env: Env,
  requestId: string,
  strategy: Strategy,
): Promise<Response> {
  await requireAdmin(request, env)
  const url = new URL(request.url)
  const offset = integerParam(url, 'offset', 0, 0, 1_000_000)
  const limit = integerParam(url, 'limit', 50, 1, 200)
  const [rows, total] = await Promise.all([
    env.DB
      .prepare(
        `SELECT * FROM virtual_strategy_trades
         WHERE strategy = ?
         ORDER BY closed_at DESC
         LIMIT ? OFFSET ?`,
      )
      .bind(strategy, limit, offset)
      .all<TradeRow>(),
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count FROM virtual_strategy_trades
         WHERE strategy = ?`,
      )
      .bind(strategy)
      .first<{ count: number }>(),
  ])
  return jsonResponse(
    {
      items: rows.results.map((row) => ({
        symbol: row.symbol,
        ...(strategy === 'intelligent' ? { side: row.side } : {}),
        leverage: row.leverage,
        entry_price: row.entry_price,
        exit_price: row.exit_price,
        quantity: row.quantity,
        pnl_usdt: row.pnl_usdt,
        pnl_pct: row.pnl_pct,
        close_reason: row.close_reason,
        opened_at: iso(row.opened_at),
        closed_at: iso(row.closed_at),
        hold_seconds: Math.max(
          0,
          Math.floor((row.closed_at - row.opened_at) / 1_000),
        ),
      })),
      total: Number(total?.count ?? 0),
    },
    200,
    requestId,
    request.method,
  )
}

async function stats(
  request: Request,
  env: Env,
  requestId: string,
  strategy: Strategy,
): Promise<Response> {
  await requireAdmin(request, env)
  const rows = await env.DB
    .prepare(
      `SELECT * FROM virtual_strategy_trades
       WHERE strategy = ? ORDER BY closed_at`,
    )
    .bind(strategy)
    .all<TradeRow>()
  const trades = rows.results
  const wins = trades.filter((row) => row.pnl_usdt > 0)
  const losses = trades.filter((row) => row.pnl_usdt < 0)
  const totalPnl = trades.reduce((sum, row) => sum + row.pnl_usdt, 0)
  const grossProfit = wins.reduce((sum, row) => sum + row.pnl_usdt, 0)
  const grossLoss = Math.abs(
    losses.reduce((sum, row) => sum + row.pnl_usdt, 0),
  )
  let equity = 0
  let peak = 0
  let maxDrawdown = 0
  for (const trade of trades) {
    equity += trade.pnl_usdt
    peak = Math.max(peak, equity)
    maxDrawdown = Math.max(maxDrawdown, peak - equity)
  }
  const byReason: Record<string, number> =
    strategy === 'managed'
      ? { tp: 0, signal: 0, timeout: 0, manual: 0 }
      : { stop_loss: 0, take_profit: 0, signal_reversal: 0 }
  for (const trade of trades) {
    byReason[trade.close_reason] = (byReason[trade.close_reason] ?? 0) + 1
  }
  return jsonResponse(
    {
      total_trades: trades.length,
      wins: wins.length,
      losses: losses.length,
      win_rate: trades.length > 0 ? wins.length / trades.length : 0,
      total_pnl: totalPnl,
      avg_pnl: trades.length > 0 ? totalPnl / trades.length : 0,
      profit_factor: grossLoss > 0 ? grossProfit / grossLoss : 0,
      max_drawdown: maxDrawdown,
      by_reason: byReason,
      ...(strategy === 'intelligent'
        ? {
            by_side: {
              long: trades.filter((row) => row.side === 'long').length,
              short: trades.filter((row) => row.side === 'short').length,
            },
          }
        : {}),
    },
    200,
    requestId,
    request.method,
  )
}

function bodyNumber(
  body: Readonly<Record<string, unknown>>,
  key: string,
  min: number,
  max: number,
): number {
  const value = Number(body[key])
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new HttpError(422, `${key} 必须在 ${min} 到 ${max} 之间`)
  }
  return value
}

async function updateAccount(
  request: Request,
  env: Env,
  requestId: string,
  strategy: Strategy,
  change: Readonly<{ column: string; value: unknown; action: string }>,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const allowed = new Set([
    'enabled',
    'open_margin',
    'open_leverage',
    'max_positions',
    'allow_long',
    'allow_short',
    'exit_tp',
    'exit_signal',
    'exit_timeout',
    'tp_pct',
  ])
  if (!allowed.has(change.column)) throw new HttpError(500, '账户字段无效')
  const timestamp = Date.now()
  await env.DB
    .prepare(
      `UPDATE virtual_strategy_accounts
       SET ${change.column} = ?, updated_at = ? WHERE strategy = ?`,
    )
    .bind(change.value, timestamp, strategy)
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: change.action,
    detail: { strategy, value: change.value },
    createdAt: timestamp,
  }).run()
  return jsonResponse(
    await statusPayload(env, strategy),
    200,
    requestId,
    request.method,
  )
}

async function toggle(
  request: Request,
  env: Env,
  requestId: string,
  strategy: Strategy,
): Promise<Response> {
  const body = await readJsonObject(request)
  if (typeof body.enabled !== 'boolean') throw new HttpError(422, 'enabled 必须为布尔值')
  return updateAccount(request, env, requestId, strategy, {
    column: 'enabled',
    value: body.enabled ? 1 : 0,
    action: `trading.${strategy}.${body.enabled ? 'enabled' : 'disabled'}`,
  })
}

async function setting(
  request: Request,
  env: Env,
  requestId: string,
  strategy: Strategy,
  kind: string,
): Promise<Response> {
  const body = await readJsonObject(request)
  if (kind === 'open-margin') {
    return updateAccount(request, env, requestId, strategy, {
      column: 'open_margin',
      value: bodyNumber(body, 'margin', 10, 10_000),
      action: `trading.${strategy}.open_margin`,
    })
  }
  if (kind === 'open-leverage') {
    return updateAccount(request, env, requestId, strategy, {
      column: 'open_leverage',
      value: Math.round(bodyNumber(body, 'leverage', 1, 20)),
      action: `trading.${strategy}.leverage`,
    })
  }
  if (kind === 'max-positions') {
    return updateAccount(request, env, requestId, strategy, {
      column: 'max_positions',
      value: Math.round(bodyNumber(body, 'max_positions', 1, 200)),
      action: `trading.${strategy}.max_positions`,
    })
  }
  if (kind === 'allow-long') {
    if (typeof body.on !== 'boolean') throw new HttpError(422, 'on 必须为布尔值')
    return updateAccount(request, env, requestId, strategy, {
      column: 'allow_long',
      value: body.on ? 1 : 0,
      action: `trading.${strategy}.allow_long`,
    })
  }
  if (kind === 'allow-direction') {
    if (!['long', 'short'].includes(String(body.which)) || typeof body.on !== 'boolean') {
      throw new HttpError(422, '方向参数无效')
    }
    return updateAccount(request, env, requestId, strategy, {
      column: body.which === 'short' ? 'allow_short' : 'allow_long',
      value: body.on ? 1 : 0,
      action: `trading.${strategy}.allow_${String(body.which)}`,
    })
  }
  if (kind === 'exit-switch') {
    if (!['tp', 'signal', 'timeout'].includes(String(body.which)) || typeof body.on !== 'boolean') {
      throw new HttpError(422, '平仓条件参数无效')
    }
    return updateAccount(request, env, requestId, strategy, {
      column: `exit_${String(body.which)}`,
      value: body.on ? 1 : 0,
      action: `trading.${strategy}.exit_${String(body.which)}`,
    })
  }
  if (kind === 'exit-tp-pct') {
    return updateAccount(request, env, requestId, strategy, {
      column: 'tp_pct',
      value: bodyNumber(body, 'pct', 0.1, 10_000),
      action: `trading.${strategy}.tp_pct`,
    })
  }
  throw new HttpError(404, '未知设置')
}

async function closePosition(
  env: Env,
  position: PositionRow,
  reason: string,
): Promise<number> {
  const realized = pnl(position)
  const closedAt = Date.now()
  await env.DB.batch([
    env.DB
      .prepare(
        `INSERT INTO virtual_strategy_trades
          (strategy, symbol, side, leverage, entry_price, exit_price, quantity,
           margin, pnl_usdt, pnl_pct, close_reason, opened_at, closed_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        position.strategy,
        position.symbol,
        position.side,
        position.leverage,
        position.entry_price,
        position.mark_price,
        position.quantity,
        position.margin,
        realized,
        realized / position.margin * 100,
        reason,
        position.opened_at,
        closedAt,
      ),
    env.DB
      .prepare(
        `UPDATE virtual_strategy_accounts
         SET cash_balance = cash_balance + ?, updated_at = ?
         WHERE strategy = ?`,
      )
      .bind(realized, closedAt, position.strategy),
    env.DB
      .prepare('DELETE FROM virtual_strategy_positions WHERE id = ?')
      .bind(position.id),
  ])
  return realized
}

async function manualClose(
  request: Request,
  env: Env,
  requestId: string,
  positionId?: number,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const target = positionId === undefined
    ? await positions(env, 'managed')
    : [
        await env.DB
          .prepare(
            `SELECT * FROM virtual_strategy_positions
             WHERE id = ? AND strategy = 'managed'`,
          )
          .bind(positionId)
          .first<PositionRow>(),
      ].filter((row): row is PositionRow => row !== null)
  if (positionId !== undefined && target.length === 0) {
    throw new HttpError(404, '持仓不存在')
  }
  let realized = 0
  for (const position of target) {
    realized += await closePosition(env, position, 'manual')
  }
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'trading.managed.manual_close',
    detail: { position_id: positionId ?? null, closed: target.length, realized },
    createdAt: Date.now(),
  }).run()
  if (positionId !== undefined) {
    return jsonResponse(
      {
        status: 'closed',
        symbol: target[0]?.symbol ?? null,
        realized_pnl: realized,
      },
      200,
      requestId,
      request.method,
    )
  }
  return jsonResponse(
    { status: 'closed', closed: target.length, total: target.length },
    200,
    requestId,
    request.method,
  )
}

async function resetIntelligent(
  request: Request,
  env: Env,
  requestId: string,
  capital?: number,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const state = await account(env, 'intelligent')
  const nextCapital = capital ?? state.initial_capital
  await env.DB.batch([
    env.DB.prepare(
      "DELETE FROM virtual_strategy_positions WHERE strategy = 'intelligent'",
    ),
    env.DB.prepare(
      "DELETE FROM virtual_strategy_trades WHERE strategy = 'intelligent'",
    ),
    env.DB
      .prepare(
        `UPDATE virtual_strategy_accounts
         SET initial_capital = ?, cash_balance = ?, updated_at = ?
         WHERE strategy = 'intelligent'`,
      )
      .bind(nextCapital, nextCapital, Date.now()),
  ])
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'trading.intelligent.reset',
    detail: { initial_capital: nextCapital },
    createdAt: Date.now(),
  }).run()
  return jsonResponse(
    await statusPayload(env, 'intelligent'),
    200,
    requestId,
    request.method,
  )
}

function strategyParams(body: Readonly<Record<string, unknown>>) {
  const weights = body.weights
  if (typeof weights !== 'object' || weights === null || Array.isArray(weights)) {
    throw new HttpError(422, 'weights 格式无效')
  }
  const weightObject = weights as Record<string, unknown>
  const normalizedWeights: Record<string, number> = {}
  for (const key of ['boll', 'macd', 'ma', 'rsi', 'kdj', 'extreme']) {
    normalizedWeights[key] = bodyNumber(weightObject, key, 0, 10)
  }
  return {
    threshold: bodyNumber(body, 'threshold', 0.1, 20),
    weights: normalizedWeights,
    atr_stop_mult: bodyNumber(body, 'atr_stop_mult', 0.1, 20),
    atr_tp_mult: bodyNumber(body, 'atr_tp_mult', 0.1, 40),
  }
}

async function getStrategyParams(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const state = await account(env, 'intelligent')
  const parsed = parseObject(state.strategy_params_json)
  return jsonResponse(
    Object.keys(parsed).length > 0 ? parsed : DEFAULT_PARAMS,
    200,
    requestId,
    request.method,
  )
}

async function setStrategyParams(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const params = strategyParams(await readJsonObject(request))
  await env.DB
    .prepare(
      `UPDATE virtual_strategy_accounts
       SET strategy_params_json = ?, updated_at = ?
       WHERE strategy = 'intelligent'`,
    )
    .bind(JSON.stringify(params), Date.now())
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'trading.intelligent.strategy_params',
    detail: params,
    createdAt: Date.now(),
  }).run()
  return jsonResponse(params, 200, requestId, request.method)
}

type Quote = Readonly<{
  symbol: string
  last_point: number
  change_pct: number
}>

async function refreshMarks(env: Env, quotes: readonly Quote[]): Promise<void> {
  const statements = quotes.map((quote) =>
    env.DB
      .prepare(
        `UPDATE virtual_strategy_positions
         SET mark_price = ? WHERE symbol = ?`,
      )
      .bind(quote.last_point, quote.symbol),
  )
  if (statements.length > 0) await env.DB.batch(statements)
}

async function runStrategy(
  env: Env,
  strategy: Strategy,
  quotes: readonly Quote[],
  klineCache: Map<string, Promise<import('./market').Kline[]>>,
): Promise<void> {
  const state = await account(env, strategy)
  if (state.enabled !== 1) return
  const params = normalizeStrategyParams(parseObject(state.strategy_params_json))
  const open = await positions(env, strategy)
  const quoteMap = new Map(quotes.map((quote) => [quote.symbol, quote]))
  for (const position of open) {
    const quote = quoteMap.get(position.symbol)
    if (!quote) continue
    const marked = { ...position, mark_price: quote.last_point }
    const percent = pnl(marked) / marked.margin * 100
    const age = Date.now() - marked.opened_at
    if (strategy === 'managed') {
      if (state.exit_tp === 1 && percent >= state.tp_pct) {
        await closePosition(env, marked, 'tp')
      } else if (state.exit_signal === 1 && quote.change_pct < 0) {
        await closePosition(env, marked, 'signal')
      } else if (state.exit_timeout === 1 && age >= 24 * 60 * 60 * 1_000) {
        await closePosition(env, marked, 'timeout')
      }
    } else if (
      (marked.side === 'long' && marked.stop_price !== null && quote.last_point <= marked.stop_price) ||
      (marked.side === 'short' && marked.stop_price !== null && quote.last_point >= marked.stop_price)
    ) {
      await closePosition(env, marked, 'stop_loss')
    } else if (
      (marked.side === 'long' && marked.tp_price !== null && quote.last_point >= marked.tp_price) ||
      (marked.side === 'short' && marked.tp_price !== null && quote.last_point <= marked.tp_price)
    ) {
      await closePosition(env, marked, 'take_profit')
    } else if (strategy === 'intelligent' && await scoreQuote(quote, params, klineCache)
      .then((signal) => Math.abs(signal.score) >= params.threshold &&
        ((marked.side === 'long' && signal.score < 0) || (marked.side === 'short' && signal.score > 0)))
      .catch(() => false)) {
      await closePosition(env, marked, 'signal_reversal')
    }
  }
  const remaining = await positions(env, strategy)
  if (remaining.length >= state.max_positions) return
  const held = new Set(remaining.map((position) => position.symbol))
  let candidate: Quote | undefined
  let side: 'long' | 'short' = 'long'
  if (strategy === 'managed') {
    candidate = quotes.find(
      (quote) => quote.change_pct >= 0.3 && !held.has(quote.symbol),
    )
    if (!candidate || state.allow_long !== 1) return
  } else {
    let scored: Awaited<ReturnType<typeof scoreQuote>> | undefined
    for (const quote of quotes.slice(0, 12)) {
      if (held.has(quote.symbol)) continue
      try {
        const output = await scoreQuote(quote, params, klineCache)
        if (Math.abs(output.score) >= params.threshold) {
          candidate = quote; scored = output; break
        }
      } catch { /* 单币种数据故障不阻塞其他候选 */ }
    }
    if (!candidate || !scored) return
    side = scored.score >= 0 ? 'long' : 'short'
    if (
      (side === 'long' && state.allow_long !== 1) ||
      (side === 'short' && state.allow_short !== 1)
    ) return
  }
  const quantity =
    state.open_margin * state.open_leverage / candidate.last_point
  const scored = strategy === 'intelligent' ? await scoreQuote(candidate, params, klineCache) : null
  const stopDistance = scored ? Math.max(scored.atr * params.atr_stop_mult, candidate.last_point * 0.001) : 0
  const stopPrice = strategy === 'intelligent'
    ? candidate.last_point + (side === 'long' ? -stopDistance : stopDistance)
    : null
  const tpPrice = strategy === 'intelligent'
    ? candidate.last_point + (side === 'long' ? scored!.atr * params.atr_tp_mult : -scored!.atr * params.atr_tp_mult)
    : null
  await env.DB
    .prepare(
      `INSERT OR IGNORE INTO virtual_strategy_positions
        (strategy, symbol, side, leverage, entry_price, quantity, margin,
         mark_price, stop_price, tp_price, signal_json, opened_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      strategy,
      candidate.symbol,
      side,
      state.open_leverage,
      candidate.last_point,
      quantity,
      state.open_margin,
      candidate.last_point,
      stopPrice,
      tpPrice,
      JSON.stringify({
        bias: side === 'long' ? '偏多' : '偏空',
        score: scored?.score ?? candidate.change_pct,
        contributions: scored?.contributions ?? { daily_change: candidate.change_pct },
      }),
      Date.now(),
    )
    .run()
}

export async function runVirtualTradingCron(env: Env): Promise<void> {
  const quotes = await env.DB
    .prepare(
      `SELECT symbol, last_point, change_pct
       FROM market_overview_quotes
       WHERE category = 'crypto' AND last_point > 0
       ORDER BY ABS(change_pct) DESC`,
    )
    .all<Quote>()
  if (quotes.results.length === 0) return
  const klineCache = new Map<string, Promise<import('./market').Kline[]>>()
  await refreshMarks(env, quotes.results)
  await runStrategy(env, 'managed', quotes.results, klineCache)
  await runStrategy(env, 'intelligent', quotes.results, klineCache)
}

export async function handleAdminTradingRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const match = /^\/api\/v1\/admin\/(managed|intelligent)(?:\/(.*))?$/u.exec(path)
  if (!match) return null
  const strategy = match[1] as Strategy
  const tail = match[2] ?? ''
  if (request.method === 'GET' && tail === 'status') {
    return getStatus(request, env, requestId, strategy)
  }
  if (request.method === 'GET' && tail === 'positions') {
    return listPositions(request, env, requestId, strategy)
  }
  if (request.method === 'GET' && tail === 'history') {
    return listHistory(request, env, requestId, strategy)
  }
  if (request.method === 'GET' && tail === 'stats') {
    return stats(request, env, requestId, strategy)
  }
  if (request.method === 'POST' && tail === 'toggle') {
    return toggle(request, env, requestId, strategy)
  }
  if (
    request.method === 'POST' &&
    [
      'open-margin',
      'open-leverage',
      'max-positions',
      'allow-long',
      'allow-direction',
      'exit-switch',
      'exit-tp-pct',
    ].includes(tail)
  ) {
    return setting(request, env, requestId, strategy, tail)
  }
  if (
    strategy === 'managed' &&
    request.method === 'POST' &&
    tail === 'positions/close-all'
  ) {
    return manualClose(request, env, requestId)
  }
  const closeMatch = /^positions\/(\d+)\/close$/u.exec(tail)
  if (strategy === 'managed' && request.method === 'POST' && closeMatch) {
    return manualClose(request, env, requestId, Number(closeMatch[1]))
  }
  if (
    strategy === 'intelligent' &&
    request.method === 'POST' &&
    tail === 'account/reset'
  ) {
    return resetIntelligent(request, env, requestId)
  }
  if (
    strategy === 'intelligent' &&
    request.method === 'POST' &&
    tail === 'account/capital'
  ) {
    const body = await readJsonObject(request)
    return resetIntelligent(
      request,
      env,
      requestId,
      bodyNumber(body, 'amount', 1, 100_000_000),
    )
  }
  if (
    strategy === 'intelligent' &&
    request.method === 'GET' &&
    tail === 'strategy-params'
  ) {
    return getStrategyParams(request, env, requestId)
  }
  if (
    strategy === 'intelligent' &&
    request.method === 'POST' &&
    tail === 'strategy-params'
  ) {
    return setStrategyParams(request, env, requestId)
  }
  return jsonResponse(
    { detail: 'Route not found' },
    404,
    requestId,
    request.method,
  )
}
