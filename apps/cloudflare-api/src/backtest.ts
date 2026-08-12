import { authenticate } from './auth'
import { HttpError, jsonResponse, readJsonObject } from './http'
import { fetchMarketKlines, type Kline } from './market'

const PERIODS = new Set(['1m', '5m', '15m', '30m', '1h', '1d', '1w'])

type BacktestRow = Readonly<{
  id: number
  user_id: string
  symbol: string
  market: string
  period: string
  start_date: string
  end_date: string
  params_json: string
  status: 'pending' | 'done' | 'error'
  metrics_json: string | null
  equity_json: string | null
  trades_json: string | null
  run_card_json: string | null
  error: string | null
  created_at: number
  updated_at: number
}>

function asObject(value: string | null): unknown {
  if (value === null) return null
  try { return JSON.parse(value) as unknown } catch { return null }
}

function serialize(row: BacktestRow, full: boolean) {
  const base = {
    id: row.id,
    symbol: row.symbol,
    market: row.market,
    period: row.period,
    start_date: row.start_date,
    end_date: row.end_date,
    status: row.status,
    created_at: new Date(row.created_at).toISOString(),
  }
  return full
    ? {
        ...base,
        params_json: asObject(row.params_json),
        metrics_json: asObject(row.metrics_json),
        equity_json: asObject(row.equity_json),
        trades_json: asObject(row.trades_json),
        run_card_json: asObject(row.run_card_json),
        error: row.error,
        updated_at: new Date(row.updated_at).toISOString(),
      }
    : base
}

function finite(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value ?? fallback)
  if (!Number.isFinite(parsed) || parsed < min || parsed > max) {
    throw new HttpError(400, `参数必须在 ${min} 到 ${max} 之间`)
  }
  return parsed
}

function mean(values: number[]): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
}

function stdev(values: number[]): number {
  const average = mean(values)
  return Math.sqrt(mean(values.map((value) => (value - average) ** 2)))
}

function maxConsecutiveLoss(values: number[]): number {
  let current = 0
  let maximum = 0
  for (const value of values) {
    current = value < 0 ? current + 1 : 0
    maximum = Math.max(maximum, current)
  }
  return maximum
}

function runSmaBacktest(
  items: Kline[],
  input: Readonly<{
    symbol: string
    initialCash: number
    fast: number
    slow: number
    leverage: number
  }>,
) {
  let cash = input.initialCash
  let quantity = 0
  let entryPrice = 0
  let entryAt = ''
  let peak = input.initialCash
  const equity: Array<Record<string, unknown>> = []
  const trades: Array<Record<string, unknown>> = []
  const completedReturns: number[] = []
  const holdings: number[] = []
  const dailyReturns: number[] = []
  let previousEquity = input.initialCash
  const benchmarkStart = items[0]!.close
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index]!
    const fastWindow = items.slice(Math.max(0, index - input.fast + 1), index + 1)
    const slowWindow = items.slice(Math.max(0, index - input.slow + 1), index + 1)
    const fast = mean(fastWindow.map((entry) => entry.close))
    const slow = mean(slowWindow.map((entry) => entry.close))
    const previousFast = index > 0
      ? mean(items.slice(Math.max(0, index - input.fast), index).map((entry) => entry.close))
      : fast
    const previousSlow = index > 0
      ? mean(items.slice(Math.max(0, index - input.slow), index).map((entry) => entry.close))
      : slow
    const crossUp = index >= input.slow && previousFast <= previousSlow && fast > slow
    const crossDown = index >= input.slow && previousFast >= previousSlow && fast < slow
    if (crossUp && quantity === 0) {
      entryPrice = item.close * 1.001
      quantity = (cash * input.leverage) / entryPrice
      entryAt = item.ts
      trades.push({
        timestamp: item.ts,
        code: input.symbol.replace('/', ''),
        side: 'buy',
        price: entryPrice,
        qty: quantity,
        reason: 'SMA golden cross',
        pnl: 0,
        holding_days: 0,
        return_pct: 0,
      })
    } else if (crossDown && quantity > 0) {
      const exitPrice = item.close * 0.999
      const pnl = (exitPrice - entryPrice) * quantity
      const returnPct = ((exitPrice - entryPrice) / entryPrice) * 100 * input.leverage
      cash += pnl
      const holdingDays = Math.max(
        0,
        (new Date(item.ts).valueOf() - new Date(entryAt).valueOf()) / 86_400_000,
      )
      completedReturns.push(returnPct / 100)
      holdings.push(holdingDays)
      trades.push({
        timestamp: item.ts,
        code: input.symbol.replace('/', ''),
        side: 'sell',
        price: exitPrice,
        qty: quantity,
        reason: 'SMA death cross',
        pnl,
        holding_days: holdingDays,
        return_pct: returnPct,
      })
      quantity = 0
      entryPrice = 0
      entryAt = ''
    }
    const currentEquity = cash + (quantity > 0 ? (item.close - entryPrice) * quantity : 0)
    peak = Math.max(peak, currentEquity)
    const drawdown = peak > 0 ? (currentEquity - peak) / peak : 0
    const ret = previousEquity > 0 ? currentEquity / previousEquity - 1 : 0
    dailyReturns.push(ret)
    previousEquity = currentEquity
    const benchmarkEquity = input.initialCash * (item.close / benchmarkStart)
    equity.push({
      timestamp: item.ts,
      equity: currentEquity,
      drawdown,
      benchmark_equity: benchmarkEquity,
      ret,
      active_ret: currentEquity / input.initialCash - item.close / benchmarkStart,
    })
  }
  const finalValue = Number(equity.at(-1)?.equity ?? input.initialCash)
  const totalReturn = finalValue / input.initialCash - 1
  const benchmarkReturn = items.at(-1)!.close / benchmarkStart - 1
  const years = Math.max(
    (new Date(items.at(-1)!.ts).valueOf() - new Date(items[0]!.ts).valueOf()) /
      (365.25 * 86_400_000),
    1 / 365.25,
  )
  const annualReturn = Math.pow(Math.max(finalValue / input.initialCash, 0.0001), 1 / years) - 1
  const maximumDrawdown = Math.min(...equity.map((point) => Number(point.drawdown)), 0)
  const volatility = stdev(dailyReturns)
  const downside = stdev(dailyReturns.filter((value) => value < 0))
  const wins = completedReturns.filter((value) => value > 0)
  const losses = completedReturns.filter((value) => value < 0)
  const grossProfit = wins.reduce((sum, value) => sum + value, 0)
  const grossLoss = Math.abs(losses.reduce((sum, value) => sum + value, 0))
  const metrics = {
    final_value: finalValue,
    total_return: totalReturn,
    annual_return: annualReturn,
    max_drawdown: maximumDrawdown,
    sharpe: volatility > 0 ? mean(dailyReturns) / volatility * Math.sqrt(252) : 0,
    calmar: maximumDrawdown < 0 ? annualReturn / Math.abs(maximumDrawdown) : 0,
    sortino: downside > 0 ? mean(dailyReturns) / downside * Math.sqrt(252) : 0,
    win_rate: completedReturns.length ? wins.length / completedReturns.length : 0,
    profit_loss_ratio: losses.length ? mean(wins) / Math.abs(mean(losses)) : 0,
    profit_factor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 99 : 0,
    max_consecutive_loss: maxConsecutiveLoss(completedReturns),
    avg_holding_days: mean(holdings),
    trade_count: completedReturns.length,
    benchmark_return: benchmarkReturn,
    excess_return: totalReturn - benchmarkReturn,
    information_ratio: volatility > 0 ? (totalReturn - benchmarkReturn) / volatility : 0,
  }
  return { metrics, equity, trades }
}

async function create(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const symbol = String(body.symbol ?? '').trim().toUpperCase()
  const market = body.market === undefined ? 'crypto' : String(body.market)
  const period = String(body.period ?? '1d')
  const start = String(body.start ?? '')
  const end = String(body.end ?? '')
  if (!symbol || market !== 'crypto' || !PERIODS.has(period)) {
    throw new HttpError(400, '当前回测仅支持 crypto 市场及有效周期')
  }
  if (!/^\d{4}-\d{2}-\d{2}$/u.test(start) || !/^\d{4}-\d{2}-\d{2}$/u.test(end) || start >= end) {
    throw new HttpError(400, 'start/end 日期范围无效')
  }
  const fast = Math.trunc(finite(body.sma_fast, 5, 2, 100))
  const slow = Math.trunc(finite(body.sma_slow, 20, 3, 300))
  if (fast >= slow) throw new HttpError(400, 'sma_fast 必须小于 sma_slow')
  const initialCash = finite(body.initial_cash, 100_000, 100, 100_000_000)
  const leverage = finite(body.leverage, 1, 1, 20)
  const params = { sma_fast: fast, sma_slow: slow, initial_cash: initialCash, leverage }
  const now = Date.now()
  const created = await env.DB.prepare(
    `INSERT INTO backtest_runs
      (user_id, symbol, market, period, start_date, end_date, params_json,
       status, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)`,
  ).bind(user.id, symbol, market, period, start, end, JSON.stringify(params), now, now).run()
  const id = Number(created.meta.last_row_id)
  try {
    const result = await fetchMarketKlines({
      symbol,
      market,
      period,
      instrument: 'spot',
      limit: 5_000,
    })
    const startAt = new Date(`${start}T00:00:00.000Z`).valueOf()
    const endAt = new Date(`${end}T23:59:59.999Z`).valueOf()
    const items = result.items.filter((item) => {
      const timestamp = new Date(item.ts).valueOf()
      return timestamp >= startAt && timestamp <= endAt
    })
    if (items.length < slow + 5) throw new Error('所选区间有效 K 线不足，请扩大日期范围')
    const output = runSmaBacktest(items, { symbol, initialCash, fast, slow, leverage })
    await env.DB.prepare(
      `UPDATE backtest_runs SET status = 'done', metrics_json = ?, equity_json = ?,
         trades_json = ?, run_card_json = ?, updated_at = ? WHERE id = ?`,
    ).bind(
      JSON.stringify(output.metrics), JSON.stringify(output.equity),
      JSON.stringify(output.trades),
      JSON.stringify({
        engine: 'cloudflare-sma-cross-v1',
        source: result.source,
        bars: items.length,
        assumptions: { commission_included: false, slippage_bps: 10 },
      }),
      Date.now(), id,
    ).run()
    return jsonResponse({ id, status: 'done' }, 201, requestId, request.method)
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : String(cause)
    await env.DB.prepare(
      `UPDATE backtest_runs SET status = 'error', error = ?, updated_at = ? WHERE id = ?`,
    ).bind(message.slice(0, 1_000), Date.now(), id).run()
    return jsonResponse({ id, status: 'error' }, 201, requestId, request.method)
  }
}

async function list(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const limit = Math.min(Math.max(Number(new URL(request.url).searchParams.get('limit') ?? 50), 1), 100)
  const rows = await env.DB.prepare(
    `SELECT * FROM backtest_runs WHERE user_id = ? ORDER BY id DESC LIMIT ?`,
  ).bind(user.id, limit).all<BacktestRow>()
  return jsonResponse(rows.results.map((row) => serialize(row, false)), 200, requestId, request.method)
}

async function detail(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  const { user } = await authenticate(request, env)
  const row = await env.DB.prepare(
    `SELECT * FROM backtest_runs WHERE id = ? AND user_id = ?`,
  ).bind(id, user.id).first<BacktestRow>()
  if (!row) throw new HttpError(404, '回测记录不存在')
  return jsonResponse(serialize(row, true), 200, requestId, request.method)
}

export async function handleBacktestRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (path === '/api/v1/backtest') {
    if (request.method === 'GET') return list(request, env, requestId)
    if (request.method === 'POST') return create(request, env, requestId)
  }
  const match = path.match(/^\/api\/v1\/backtest\/(\d+)$/u)
  if (match?.[1] && request.method === 'GET') {
    return detail(request, env, requestId, Number(match[1]))
  }
  return path.startsWith('/api/v1/backtest')
    ? jsonResponse({ detail: 'Route not found' }, 404, requestId, request.method)
    : null
}
