import { fetchMarketKlines, type Kline } from './market'

export type StrategyParams = Readonly<{
  threshold: number
  weights: Record<'boll' | 'macd' | 'ma' | 'rsi' | 'kdj' | 'extreme', number>
  atr_stop_mult: number
  atr_tp_mult: number
}>

export const DEFAULT_STRATEGY_PARAMS: StrategyParams = {
  threshold: 3,
  weights: { boll: 1, macd: 1, ma: 1, rsi: 1, kdj: 1, extreme: 1 },
  atr_stop_mult: 2,
  atr_tp_mult: 4,
}

export function normalizeStrategyParams(value: Record<string, unknown>): StrategyParams {
  const weights = typeof value.weights === 'object' && value.weights !== null && !Array.isArray(value.weights)
    ? value.weights as Record<string, unknown>
    : {}
  return {
    threshold: Number(value.threshold ?? DEFAULT_STRATEGY_PARAMS.threshold),
    weights: Object.fromEntries(Object.entries(DEFAULT_STRATEGY_PARAMS.weights).map(
      ([key, fallback]) => [key, Number(weights[key] ?? fallback)],
    )) as StrategyParams['weights'],
    atr_stop_mult: Number(value.atr_stop_mult ?? DEFAULT_STRATEGY_PARAMS.atr_stop_mult),
    atr_tp_mult: Number(value.atr_tp_mult ?? DEFAULT_STRATEGY_PARAMS.atr_tp_mult),
  }
}

const mean = (values: readonly number[]) =>
  values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1)

function ema(values: readonly number[], period: number): number[] {
  const alpha = 2 / (period + 1)
  return values.reduce<number[]>((rows, value) => {
    rows.push(rows.length ? value * alpha + rows.at(-1)! * (1 - alpha) : value)
    return rows
  }, [])
}

function rsi(closes: readonly number[]): number {
  let gains = 0; let losses = 0
  for (let index = Math.max(1, closes.length - 14); index < closes.length; index += 1) {
    const change = closes[index]! - closes[index - 1]!
    if (change >= 0) gains += change
    else losses -= change
  }
  return losses === 0 ? (gains > 0 ? 100 : 50) : 100 - 100 / (1 + gains / losses)
}

export function scoreStrategy(
  items: readonly Kline[],
  params: StrategyParams,
  dailyChange: number,
) {
  const closes = items.map((item) => item.close)
  const latest = items.at(-1)
  if (!latest || items.length < 26) throw new Error('策略评分至少需要 26 根 K 线')
  const window = closes.slice(-20)
  const middle = mean(window)
  const deviation = Math.sqrt(mean(window.map((value) => (value - middle) ** 2)))
  const pctB = deviation === 0 ? 50 : (latest.close - (middle - deviation * 2)) / (deviation * 4) * 100
  const fast = ema(closes, 12); const slow = ema(closes, 26)
  const macd = closes.map((_, index) => fast[index]! - slow[index]!)
  const histogram = macd.at(-1)! - ema(macd, 9).at(-1)!
  const stochastic = items.slice(-9)
  const low = Math.min(...stochastic.map((item) => item.low))
  const high = Math.max(...stochastic.map((item) => item.high))
  const k = high === low ? 50 : (latest.close - low) / (high - low) * 100
  const rsi14 = rsi(closes)
  const contributions = {
    boll: pctB < 20 ? 1 : pctB > 80 ? -1 : 0,
    macd: histogram > 0 ? 1 : histogram < 0 ? -1 : 0,
    ma: mean(closes.slice(-5)) >= middle ? 1 : -1,
    rsi: rsi14 < 40 ? 1 : rsi14 > 60 ? -1 : 0,
    kdj: k < 30 ? 1 : k > 70 ? -1 : 0,
    extreme: dailyChange >= 8 ? -1 : dailyChange <= -8 ? 1 : 0,
  } as const
  const score = Object.entries(contributions).reduce(
    (sum, [key, value]) => sum + value * params.weights[key as keyof typeof params.weights],
    0,
  )
  const trueRanges = items.slice(-14).map((item, index, rows) => {
    const previous = rows[index - 1]?.close ?? item.open
    return Math.max(item.high - item.low, Math.abs(item.high - previous), Math.abs(item.low - previous))
  })
  return {
    score,
    bias: score > 0 ? '偏多' : score < 0 ? '偏空' : '中性',
    contributions,
    atr: mean(trueRanges),
  }
}

export async function scoreQuote(
  quote: Readonly<{ symbol: string; change_pct: number }>,
  params: StrategyParams,
  cache: Map<string, Promise<Kline[]>>,
) {
  let pending = cache.get(quote.symbol)
  if (!pending) {
    pending = fetchMarketKlines({
      symbol: quote.symbol, market: 'crypto', period: '1h', instrument: 'perp', limit: 120,
    }).then((result) => result.items)
    cache.set(quote.symbol, pending)
  }
  return scoreStrategy(await pending, params, quote.change_pct)
}
