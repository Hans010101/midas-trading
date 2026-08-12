import { authenticate } from './auth'
import { HttpError, jsonResponse, readJsonObject } from './http'

type Strategy = 'managed' | 'intelligent'

type Account = Readonly<{
  user_id: string
  strategy: Strategy
  enabled: number
  initial_capital: number
  cash_balance: number
  open_margin: number
  open_leverage: number
  max_positions: number
  allow_long: number
  allow_short: number
  strategy_params_json: string
}>

type Position = Readonly<{
  id: number
  user_id: string
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

type Trade = Readonly<{
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

const DEFAULT_PARAMS = {
  threshold: 3,
  weights: { boll: 1, macd: 1, ma: 1, rsi: 1, kdj: 1, extreme: 1 },
  atr_stop_mult: 2,
  atr_tp_mult: 4,
}

function parseObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value) as unknown
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {}
  } catch { return {} }
}

function positionPnl(position: Position): number {
  const direction = position.side === 'long' ? 1 : -1
  return (position.mark_price - position.entry_price) * position.quantity * direction
}

async function ensureAccount(env: Env, userId: string, strategy: Strategy): Promise<Account> {
  const now = Date.now()
  await env.DB.prepare(
    `INSERT OR IGNORE INTO user_strategy_accounts
      (user_id, strategy, strategy_params_json, updated_at)
     VALUES (?, ?, ?, ?)`,
  ).bind(userId, strategy, strategy === 'intelligent' ? JSON.stringify(DEFAULT_PARAMS) : '{}', now).run()
  const row = await env.DB.prepare(
    'SELECT * FROM user_strategy_accounts WHERE user_id = ? AND strategy = ?',
  ).bind(userId, strategy).first<Account>()
  if (!row) throw new HttpError(500, '自动策略账户创建失败')
  return row
}

async function ownedPositions(env: Env, userId: string, strategy: Strategy): Promise<Position[]> {
  const rows = await env.DB.prepare(
    `SELECT * FROM user_strategy_positions
     WHERE user_id = ? AND strategy = ? ORDER BY opened_at DESC`,
  ).bind(userId, strategy).all<Position>()
  return rows.results
}

async function status(env: Env, userId: string, strategy: Strategy) {
  const [account, positions] = await Promise.all([
    ensureAccount(env, userId, strategy),
    ownedPositions(env, userId, strategy),
  ])
  const unrealized = positions.reduce((sum, item) => sum + positionPnl(item), 0)
  const occupiedMargin = positions.reduce((sum, item) => sum + item.margin, 0)
  const accountValue = account.cash_balance + unrealized
  return {
    enabled: account.enabled === 1,
    account_ready: true,
    account_value: accountValue,
    cash_balance: account.cash_balance,
    initial_capital: account.initial_capital,
    open_positions: positions.length,
    open_margin: account.open_margin,
    open_leverage: account.open_leverage,
    max_positions: account.max_positions,
    allow_long: account.allow_long === 1,
    ...(strategy === 'managed'
      ? { available_funds: accountValue - occupiedMargin, occupied_margin: occupiedMargin,
          exit_tp: true, exit_signal: true, exit_timeout: true, tp_pct: 100 }
      : { allow_short: account.allow_short === 1 }),
  }
}

async function stats(env: Env, userId: string, strategy: Strategy) {
  const rows = await env.DB.prepare(
    `SELECT * FROM user_strategy_trades
     WHERE user_id = ? AND strategy = ? ORDER BY closed_at`,
  ).bind(userId, strategy).all<Trade>()
  const trades = rows.results
  const wins = trades.filter((item) => item.pnl_usdt > 0)
  const losses = trades.filter((item) => item.pnl_usdt < 0)
  const total = trades.reduce((sum, item) => sum + item.pnl_usdt, 0)
  const grossProfit = wins.reduce((sum, item) => sum + item.pnl_usdt, 0)
  const grossLoss = Math.abs(losses.reduce((sum, item) => sum + item.pnl_usdt, 0))
  let equity = 0; let peak = 0; let maxDrawdown = 0
  for (const trade of trades) {
    equity += trade.pnl_usdt; peak = Math.max(peak, equity)
    maxDrawdown = Math.max(maxDrawdown, peak - equity)
  }
  const byReason: Record<string, number> = strategy === 'managed'
    ? { tp: 0, signal: 0, timeout: 0, manual: 0 }
    : { stop_loss: 0, take_profit: 0, signal_reversal: 0 }
  for (const trade of trades) byReason[trade.close_reason] = (byReason[trade.close_reason] ?? 0) + 1
  return {
    total_trades: trades.length, wins: wins.length, losses: losses.length,
    win_rate: trades.length ? wins.length / trades.length : 0,
    total_pnl: total, avg_pnl: trades.length ? total / trades.length : 0,
    profit_factor: grossLoss ? grossProfit / grossLoss : 0, max_drawdown: maxDrawdown,
    by_reason: byReason,
    ...(strategy === 'intelligent' ? { by_side: {
      long: trades.filter((item) => item.side === 'long').length,
      short: trades.filter((item) => item.side === 'short').length,
    } } : {}),
  }
}

function numberField(body: Record<string, unknown>, key: string, min: number, max: number): number {
  const value = Number(body[key])
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new HttpError(422, `${key} 必须在 ${min}–${max} 之间`)
  }
  return value
}

async function closePosition(env: Env, position: Position, reason: string): Promise<number> {
  const realized = positionPnl(position)
  const now = Date.now()
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO user_strategy_trades
        (user_id,strategy,symbol,side,leverage,entry_price,exit_price,quantity,
         margin,pnl_usdt,pnl_pct,close_reason,opened_at,closed_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
    ).bind(position.user_id, position.strategy, position.symbol, position.side,
      position.leverage, position.entry_price, position.mark_price, position.quantity,
      position.margin, realized, realized / position.margin * 100, reason,
      position.opened_at, now),
    env.DB.prepare(
      `UPDATE user_strategy_accounts SET cash_balance=cash_balance+?,updated_at=?
       WHERE user_id=? AND strategy=?`,
    ).bind(realized, now, position.user_id, position.strategy),
    env.DB.prepare('DELETE FROM user_strategy_positions WHERE id=?').bind(position.id),
  ])
  return realized
}

export async function handleUserStrategyRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const match = /^\/api\/v1\/platinum\/(managed|intelligent)(?:\/(.*))?$/u.exec(path)
  if (!match) return null
  const strategy = match[1] as Strategy
  const tail = match[2] ?? ''
  const { user } = await authenticate(request, env)
  const account = await ensureAccount(env, user.id, strategy)
  if (request.method === 'GET' && tail === 'status') {
    return jsonResponse(await status(env, user.id, strategy), 200, requestId, request.method)
  }
  if (request.method === 'GET' && tail === 'positions') {
    const items = (await ownedPositions(env, user.id, strategy)).map((item) => ({
      id: item.id, symbol: item.symbol, side: item.side, leverage: item.leverage,
      entry_price: item.entry_price, quantity: item.quantity, margin: item.margin,
      opened_at: new Date(item.opened_at).toISOString(), mark: item.mark_price,
      unrealized_pnl: positionPnl(item), unrealized_pct: positionPnl(item) / item.margin * 100,
      stop_price: item.stop_price, tp_price: item.tp_price,
      signals: parseObject(item.signal_json), bias: String(parseObject(item.signal_json).bias ?? '中性'),
    }))
    return jsonResponse({ items, total: items.length }, 200, requestId, request.method)
  }
  if (request.method === 'GET' && tail === 'history') {
    const rows = await env.DB.prepare(
      `SELECT * FROM user_strategy_trades WHERE user_id=? AND strategy=?
       ORDER BY closed_at DESC LIMIT 200`,
    ).bind(user.id, strategy).all<Trade>()
    return jsonResponse({ items: rows.results.map((item) => ({ ...item,
      opened_at: new Date(item.opened_at).toISOString(),
      closed_at: new Date(item.closed_at).toISOString(),
      hold_seconds: Math.floor((item.closed_at - item.opened_at) / 1000),
    })), total: rows.results.length }, 200, requestId, request.method)
  }
  if (request.method === 'GET' && tail === 'stats') {
    return jsonResponse(await stats(env, user.id, strategy), 200, requestId, request.method)
  }
  if (request.method === 'GET' && tail === 'strategy-params' && strategy === 'intelligent') {
    return jsonResponse(parseObject(account.strategy_params_json), 200, requestId, request.method)
  }
  const body = request.method === 'POST' ? await readJsonObject(request) : {}
  if (request.method === 'POST' && tail === 'toggle') {
    if (typeof body.enabled !== 'boolean') throw new HttpError(422, 'enabled 必须为布尔值')
    await env.DB.prepare(
      `UPDATE user_strategy_accounts SET enabled=?,updated_at=? WHERE user_id=? AND strategy=?`,
    ).bind(body.enabled ? 1 : 0, Date.now(), user.id, strategy).run()
  } else if (request.method === 'POST' && ['open-margin','open-leverage','max-positions'].includes(tail)) {
    const setting = tail === 'open-margin'
      ? ['open_margin', numberField(body, 'margin', 10, 10_000)] as const
      : tail === 'open-leverage'
        ? ['open_leverage', Math.round(numberField(body, 'leverage', 1, 20))] as const
        : ['max_positions', Math.round(numberField(body, 'max_positions', 1, 50))] as const
    await env.DB.prepare(
      `UPDATE user_strategy_accounts SET ${setting[0]}=?,updated_at=? WHERE user_id=? AND strategy=?`,
    ).bind(setting[1], Date.now(), user.id, strategy).run()
  } else if (request.method === 'POST' && (tail === 'allow-direction' || tail === 'allow-long')) {
    if (typeof body.on !== 'boolean') throw new HttpError(422, 'on 必须为布尔值')
    const column = tail === 'allow-direction' && body.which === 'short' ? 'allow_short' : 'allow_long'
    await env.DB.prepare(
      `UPDATE user_strategy_accounts SET ${column}=?,updated_at=? WHERE user_id=? AND strategy=?`,
    ).bind(body.on ? 1 : 0, Date.now(), user.id, strategy).run()
  } else if (request.method === 'POST' && tail === 'strategy-params' && strategy === 'intelligent') {
    const threshold = numberField(body, 'threshold', 0.1, 20)
    const atrStop = numberField(body, 'atr_stop_mult', 0.1, 20)
    const atrTp = numberField(body, 'atr_tp_mult', 0.1, 50)
    const weights = body.weights
    if (!weights || typeof weights !== 'object' || Array.isArray(weights)) {
      throw new HttpError(422, 'weights 必须是权重对象')
    }
    const safeWeights = Object.fromEntries(
      Object.keys(DEFAULT_PARAMS.weights).map((key) => {
        const value = Number((weights as Record<string, unknown>)[key])
        if (!Number.isFinite(value) || value < 0 || value > 10) {
          throw new HttpError(422, `${key} 权重必须在 0–10 之间`)
        }
        return [key, value]
      }),
    )
    const params = {
      threshold,
      weights: safeWeights,
      atr_stop_mult: atrStop,
      atr_tp_mult: atrTp,
    }
    await env.DB.prepare(
      `UPDATE user_strategy_accounts SET strategy_params_json=?,updated_at=?
       WHERE user_id=? AND strategy='intelligent'`,
    ).bind(JSON.stringify(params), Date.now(), user.id).run()
    return jsonResponse(params, 200, requestId, request.method)
  } else if (request.method === 'POST' && (tail === 'account/reset' || tail === 'account/capital')) {
    const capital = tail === 'account/capital'
      ? numberField(body, 'amount', 100, 100_000_000)
      : account.initial_capital
    await env.DB.batch([
      env.DB.prepare('DELETE FROM user_strategy_positions WHERE user_id=? AND strategy=?').bind(user.id, strategy),
      env.DB.prepare('DELETE FROM user_strategy_trades WHERE user_id=? AND strategy=?').bind(user.id, strategy),
      env.DB.prepare(
        `UPDATE user_strategy_accounts SET initial_capital=?,cash_balance=?,enabled=0,updated_at=?
         WHERE user_id=? AND strategy=?`,
      ).bind(capital, capital, Date.now(), user.id, strategy),
    ])
  } else if (request.method === 'POST' && tail === 'positions/close-all' && strategy === 'managed') {
    const positions = await ownedPositions(env, user.id, strategy)
    for (const position of positions) await closePosition(env, position, 'manual')
    return jsonResponse({ status: 'closed', closed: positions.length, total: positions.length }, 200, requestId, request.method)
  } else {
    const close = /^positions\/(\d+)\/close$/u.exec(tail)
    if (!close || request.method !== 'POST' || strategy !== 'managed') return null
    const position = await env.DB.prepare(
      `SELECT * FROM user_strategy_positions WHERE id=? AND user_id=? AND strategy='managed'`,
    ).bind(Number(close[1]), user.id).first<Position>()
    if (!position) throw new HttpError(404, '持仓不存在')
    const realized = await closePosition(env, position, 'manual')
    return jsonResponse({ status: 'closed', symbol: position.symbol, realized_pnl: realized }, 200, requestId, request.method)
  }
  return jsonResponse(await status(env, user.id, strategy), 200, requestId, request.method)
}

type Quote = Readonly<{ symbol: string; last_point: number; change_pct: number }>

export async function runUserStrategiesCron(env: Env): Promise<void> {
  const [accounts, quotes] = await Promise.all([
    env.DB.prepare("SELECT * FROM user_strategy_accounts WHERE enabled=1 ORDER BY updated_at LIMIT 200").all<Account>(),
    env.DB.prepare(
      `SELECT symbol,last_point,change_pct FROM market_overview_quotes
       WHERE category='crypto' AND last_point>0 ORDER BY ABS(change_pct) DESC LIMIT 80`,
    ).all<Quote>(),
  ])
  if (!quotes.results.length) return
  for (const account of accounts.results) {
    const positions = await ownedPositions(env, account.user_id, account.strategy)
    const quoteMap = new Map(quotes.results.map((item) => [item.symbol, item]))
    for (const position of positions) {
      const quote = quoteMap.get(position.symbol)
      if (!quote) continue
      await env.DB.prepare('UPDATE user_strategy_positions SET mark_price=? WHERE id=?')
        .bind(quote.last_point, position.id).run()
      const marked = { ...position, mark_price: quote.last_point }
      const pnlPct = positionPnl(marked) / marked.margin * 100
      if (account.strategy === 'managed' && (pnlPct >= 100 || quote.change_pct < 0 || Date.now() - marked.opened_at >= 86_400_000)) {
        await closePosition(env, marked, pnlPct >= 100 ? 'tp' : quote.change_pct < 0 ? 'signal' : 'timeout')
      } else if (account.strategy === 'intelligent' && (
        (marked.side === 'long' && marked.stop_price !== null && quote.last_point <= marked.stop_price) ||
        (marked.side === 'short' && marked.stop_price !== null && quote.last_point >= marked.stop_price) ||
        (marked.side === 'long' && marked.tp_price !== null && quote.last_point >= marked.tp_price) ||
        (marked.side === 'short' && marked.tp_price !== null && quote.last_point <= marked.tp_price)
      )) await closePosition(env, marked, pnlPct > 0 ? 'take_profit' : 'stop_loss')
    }
    const remaining = await ownedPositions(env, account.user_id, account.strategy)
    if (remaining.length >= account.max_positions) continue
    const held = new Set(remaining.map((item) => item.symbol))
    const threshold = account.strategy === 'intelligent'
      ? Number(parseObject(account.strategy_params_json).threshold ?? 3)
      : 0.3
    const candidate = quotes.results.find((item) => Math.abs(item.change_pct) >= threshold && !held.has(item.symbol))
    if (!candidate) continue
    const side = account.strategy === 'managed' || candidate.change_pct >= 0 ? 'long' : 'short'
    if ((side === 'long' && !account.allow_long) || (side === 'short' && !account.allow_short)) continue
    const distance = Math.max(0.01, Math.abs(candidate.change_pct) / 100) * candidate.last_point
    await env.DB.prepare(
      `INSERT OR IGNORE INTO user_strategy_positions
        (user_id,strategy,symbol,side,leverage,entry_price,quantity,margin,
         mark_price,stop_price,tp_price,signal_json,opened_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,
    ).bind(account.user_id, account.strategy, candidate.symbol, side, account.open_leverage,
      candidate.last_point, account.open_margin * account.open_leverage / candidate.last_point,
      account.open_margin, candidate.last_point,
      account.strategy === 'intelligent' ? candidate.last_point + (side === 'long' ? -distance : distance) : null,
      account.strategy === 'intelligent' ? candidate.last_point + (side === 'long' ? distance * 2 : -distance * 2) : null,
      JSON.stringify({ bias: side === 'long' ? '偏多' : '偏空', score: Math.abs(candidate.change_pct), contributions: { daily_change: candidate.change_pct } }),
      Date.now()).run()
  }
}
