import { authenticate } from './auth'
import { invokeAi, parseAiJson } from './ai-provider'
import { fetchCryptoAiContext } from './crypto-market'
import {
  HttpError,
  bearerToken,
  jsonResponse,
  readJsonObject,
} from './http'
import { fetchMarketKlines, type Kline } from './market'

const MARKETS = new Set(['cn', 'us', 'hk', 'crypto'])
const PERIODS = new Set(['1m', '5m', '15m', '30m', '1h', '1d', '1w'])
const STRATEGIES = new Set([
  'ma_cross',
  'rsi_reversal',
  'boll_reversion',
  'macd_cross',
  'kdj_cross',
  'extreme',
])

function finite(value: unknown, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function bounded(value: unknown, min: number, max: number, fallback: number) {
  return Math.min(max, Math.max(min, finite(value, fallback)))
}

function average(values: readonly number[]): number {
  return values.length > 0
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : 0
}

function sma(items: readonly Kline[], size: number): number {
  return average(items.slice(-size).map((item) => item.close))
}

function rsi(items: readonly Kline[], size = 14): number {
  const closes = items.slice(-(size + 1)).map((item) => item.close)
  if (closes.length < 2) return 50
  let gains = 0
  let losses = 0
  for (let index = 1; index < closes.length; index += 1) {
    const change = (closes[index] ?? 0) - (closes[index - 1] ?? 0)
    if (change >= 0) gains += change
    else losses -= change
  }
  if (losses === 0) return gains > 0 ? 100 : 50
  const relativeStrength = gains / losses
  return 100 - 100 / (1 + relativeStrength)
}

function volatility(items: readonly Kline[]): number {
  const returns = items.slice(-21).flatMap((item, index, rows) => {
    const previous = rows[index - 1]?.close
    return previous && previous > 0 ? [(item.close - previous) / previous] : []
  })
  if (returns.length === 0) return 0
  const mean = average(returns)
  return Math.sqrt(average(returns.map((value) => (value - mean) ** 2))) * 100
}

function compositeLabel(score: number) {
  if (score >= 60) return '强多'
  if (score >= 20) return '弱多'
  if (score <= -60) return '强空'
  if (score <= -20) return '弱空'
  return '中性'
}

type StrategySignal = {
  ts: string
  price: number
  kind: 'buy' | 'sell'
  reason: string
  levels: Record<string, number>
  strength: number | null
  strength_note: string | null
}

function smaAt(items: readonly Kline[], index: number, size: number): number {
  if (index + 1 < size) return Number.NaN
  return average(
    items.slice(index + 1 - size, index + 1).map((item) => item.close),
  )
}

function rsiAt(items: readonly Kline[], index: number, size = 14): number {
  if (index < size) return 50
  return rsi(items.slice(index - size, index + 1), size)
}

function bollAt(items: readonly Kline[], index: number) {
  const values = items
    .slice(Math.max(0, index - 19), index + 1)
    .map((item) => item.close)
  const middle = average(values)
  const deviation = Math.sqrt(
    average(values.map((value) => (value - middle) ** 2)),
  )
  return {
    middle,
    upper: middle + deviation * 2,
    lower: middle - deviation * 2,
  }
}

function emaSeries(values: readonly number[], size: number): number[] {
  const alpha = 2 / (size + 1)
  const result: number[] = []
  values.forEach((value, index) => {
    result.push(
      index === 0
        ? value
        : value * alpha + (result[index - 1] ?? value) * (1 - alpha),
    )
  })
  return result
}

function signal(
  item: Kline,
  kind: 'buy' | 'sell',
  reason: string,
  levels: Record<string, number>,
  strength: number | null = null,
  strengthNote: string | null = null,
): StrategySignal {
  return {
    ts: item.ts,
    price: item.close,
    kind,
    reason,
    levels,
    strength,
    strength_note: strengthNote,
  }
}

function scanStrategy(
  items: readonly Kline[],
  strategy: string,
): StrategySignal[] {
  const signals: StrategySignal[] = []
  const closes = items.map((item) => item.close)
  const ema12 = emaSeries(closes, 12)
  const ema26 = emaSeries(closes, 26)
  const macd = ema12.map((value, index) => value - (ema26[index] ?? value))
  const macdSignal = emaSeries(macd, 9)
  let previousK = 50
  let previousD = 50

  for (let index = 1; index < items.length; index += 1) {
    const item = items[index] as Kline
    if (strategy === 'ma_cross' && index >= 20) {
      const fast = smaAt(items, index, 5)
      const slow = smaAt(items, index, 20)
      const previousFast = smaAt(items, index - 1, 5)
      const previousSlow = smaAt(items, index - 1, 20)
      if (previousFast <= previousSlow && fast > slow) {
        signals.push(signal(item, 'buy', 'MA5 上穿 MA20', { MA5: fast, MA20: slow }))
      } else if (previousFast >= previousSlow && fast < slow) {
        signals.push(signal(item, 'sell', 'MA5 下穿 MA20', { MA5: fast, MA20: slow }))
      }
    } else if (strategy === 'rsi_reversal' && index >= 15) {
      const current = rsiAt(items, index)
      const previous = rsiAt(items, index - 1)
      if (previous <= 30 && current > 30) {
        signals.push(signal(item, 'buy', 'RSI 从超卖区回升', { RSI: current, 超卖线: 30 }, 30 - previous, `RSI 探至 ${previous.toFixed(1)}`))
      } else if (previous >= 70 && current < 70) {
        signals.push(signal(item, 'sell', 'RSI 从超买区回落', { RSI: current, 超买线: 70 }, previous - 70, `RSI 升至 ${previous.toFixed(1)}`))
      }
    } else if (strategy === 'boll_reversion' && index >= 20) {
      const current = bollAt(items, index)
      const previous = bollAt(items, index - 1)
      const previousClose = items[index - 1]?.close ?? item.close
      if (previousClose <= previous.lower && item.close > current.lower) {
        const distance = Math.abs(previousClose - previous.lower) / previous.lower * 100
        signals.push(signal(item, 'buy', '价格从布林下轨外回归', { 上轨: current.upper, 中轨: current.middle, 下轨: current.lower }, distance, `偏离下轨 ${distance.toFixed(1)}%`))
      } else if (previousClose >= previous.upper && item.close < current.upper) {
        const distance = Math.abs(previousClose - previous.upper) / previous.upper * 100
        signals.push(signal(item, 'sell', '价格从布林上轨外回归', { 上轨: current.upper, 中轨: current.middle, 下轨: current.lower }, distance, `偏离上轨 ${distance.toFixed(1)}%`))
      }
    } else if (strategy === 'macd_cross' && index >= 26) {
      const currentDiff = (macd[index] ?? 0) - (macdSignal[index] ?? 0)
      const previousDiff = (macd[index - 1] ?? 0) - (macdSignal[index - 1] ?? 0)
      if (previousDiff <= 0 && currentDiff > 0) {
        signals.push(signal(item, 'buy', 'MACD 金叉', { DIF: macd[index] ?? 0, DEA: macdSignal[index] ?? 0 }))
      } else if (previousDiff >= 0 && currentDiff < 0) {
        signals.push(signal(item, 'sell', 'MACD 死叉', { DIF: macd[index] ?? 0, DEA: macdSignal[index] ?? 0 }))
      }
    } else if (strategy === 'kdj_cross' && index >= 9) {
      const window = items.slice(index - 8, index + 1)
      const low = Math.min(...window.map((row) => row.low))
      const high = Math.max(...window.map((row) => row.high))
      const rsv = high === low ? 50 : (item.close - low) / (high - low) * 100
      const currentK = previousK * 2 / 3 + rsv / 3
      const currentD = previousD * 2 / 3 + currentK / 3
      if (previousK <= previousD && currentK > currentD) {
        signals.push(signal(item, 'buy', 'KDJ 金叉', { K: currentK, D: currentD }))
      } else if (previousK >= previousD && currentK < currentD) {
        signals.push(signal(item, 'sell', 'KDJ 死叉', { K: currentK, D: currentD }))
      }
      previousK = currentK
      previousD = currentD
    }
  }
  return signals
}

function strategyParams(url: URL) {
  const symbol = url.searchParams.get('symbol')?.trim() ?? ''
  const market = url.searchParams.get('market') ?? ''
  const period = url.searchParams.get('period') ?? '1d'
  const instrument = url.searchParams.get('instrument') ?? 'spot'
  const limit = Math.min(1_000, Number(url.searchParams.get('limit') ?? '300'))
  if (
    !symbol ||
    !MARKETS.has(market) ||
    !PERIODS.has(period) ||
    !Number.isSafeInteger(limit) ||
    limit < 30 ||
    (instrument !== 'spot' && instrument !== 'perp') ||
    (instrument === 'perp' && market !== 'crypto')
  ) {
    throw new HttpError(400, '策略参数格式无效')
  }
  return { symbol, market, period, instrument, limit }
}

async function strategySignals(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const url = new URL(request.url)
  const params = strategyParams(url)
  const strategy = url.searchParams.get('strategy') ?? ''
  if (!STRATEGIES.has(strategy)) throw new HttpError(400, '策略类型无效')
  if (!bearerToken(request)) {
    return jsonResponse({
      ...params,
      strategy,
      bar_count: 0,
      signals: [],
      current_triggered: false,
      last_signal: null,
      locked: true,
    }, 200, requestId, request.method)
  }
  await authenticate(request, env)
  const klines = await fetchMarketKlines({
    ...params,
    instrument: params.instrument as 'spot' | 'perp',
  })
  const signals = strategy === 'extreme'
    ? []
    : scanStrategy(klines.items, strategy)
  const lastSignal = signals.at(-1) ?? null
  return jsonResponse({
    ...params,
    strategy,
    bar_count: klines.items.length,
    signals,
    current_triggered:
      lastSignal?.ts === klines.items.at(-1)?.ts,
    last_signal: lastSignal,
    locked: false,
  }, 200, requestId, request.method)
}

async function strategyRecommend(
  request: Request,
  requestId: string,
): Promise<Response> {
  const params = strategyParams(new URL(request.url))
  const klines = await fetchMarketKlines({
    ...params,
    instrument: params.instrument as 'spot' | 'perp',
  })
  const items = klines.items
  const last = items.at(-1) as Kline
  const previous = items.at(-21) ?? items[0] as Kline
  const trend = previous.close === 0 ? 0 : (last.close - previous.close) / previous.close
  const currentRsi = rsi(items)
  const boll = bollAt(items, items.length - 1)
  const percentB = boll.upper === boll.lower
    ? 0.5
    : (last.close - boll.lower) / (boll.upper - boll.lower)
  let recommended = 'ma_cross'
  let reason = '当前方向性有限，优先观察均线交叉确认趋势启动'
  if (Math.abs(trend) >= 0.03) {
    reason = trend > 0
      ? '近 20 根 K 线趋势向上，均线交叉更适合跟踪趋势'
      : '近 20 根 K 线趋势向下，均线交叉更适合跟踪趋势'
  } else if (currentRsi <= 35 || currentRsi >= 65) {
    recommended = 'rsi_reversal'
    reason = `震荡结构中 RSI ${currentRsi.toFixed(1)} 接近极值区，关注反转确认`
  } else if (percentB <= 0.2 || percentB >= 0.8) {
    recommended = 'boll_reversion'
    reason = '震荡结构中价格接近布林轨道，适合观察均值回归'
  }
  return jsonResponse({
    ...params,
    recommended_strategy: recommended,
    reason,
  }, 200, requestId, request.method)
}

function lockedCard(
  symbol: string,
  market: string,
  period: string,
  requestId: string,
  method: string,
) {
  return jsonResponse({
    symbol,
    market,
    period,
    generated_at: new Date().toISOString(),
    composite_score: 0,
    composite_label: '中性',
    composite_confidence: 0,
    agent_scores: [],
    contradiction: null,
    narrative: '',
    chan_signals: [],
    actionable: null,
    trading_plan: null,
    event_risk: null,
    disclaimer: '',
    cached: false,
    token_usage: 0,
    llm_mode: 'real',
    llm_provider: null,
    locked: true,
  }, 200, requestId, method)
}

function keyLevels(value: unknown, items: readonly Kline[]): number[] {
  const parsed = Array.isArray(value)
    ? value.map((item) => finite(item)).filter((item) => item > 0).slice(0, 4)
    : []
  if (parsed.length > 0) return parsed
  const recent = items.slice(-20)
  return [
    Math.min(...recent.map((item) => item.low)),
    Math.max(...recent.map((item) => item.high)),
  ]
}

function tradingPlan(
  score: number,
  close: number,
  levels: readonly number[],
  planNote: string,
) {
  if (Math.abs(score) < 20) return null
  const direction = score > 0 ? 'long' : 'short'
  const support = Math.min(...levels, close * 0.98)
  const resistance = Math.max(...levels, close * 1.02)
  const entryLow = direction === 'long' ? support : close * 0.995
  const entryHigh = direction === 'long' ? close * 1.005 : resistance
  const stop = direction === 'long' ? support * 0.985 : resistance * 1.015
  const risk = Math.max(Math.abs(close - stop), close * 0.005)
  return {
    direction,
    entry_low: entryLow,
    entry_high: entryHigh,
    stop,
    target1: direction === 'long' ? close + risk * 1.5 : close - risk * 1.5,
    target2: direction === 'long' ? close + risk * 2.5 : close - risk * 2.5,
    risk_reward: 2,
    plan_note: planNote,
  }
}

async function decisionCard(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const url = new URL(request.url)
  const symbol = url.searchParams.get('symbol')?.trim() ?? ''
  const market = url.searchParams.get('market') ?? ''
  const period = url.searchParams.get('period') ?? '1d'
  const instrument = url.searchParams.get('instrument') ?? 'spot'
  const limit = Math.min(300, Number(url.searchParams.get('limit') ?? '300'))
  if (
    !symbol ||
    !MARKETS.has(market) ||
    !PERIODS.has(period) ||
    !Number.isSafeInteger(limit) ||
    limit < 30 ||
    (instrument !== 'spot' && instrument !== 'perp')
  ) {
    throw new HttpError(400, 'AI 决策卡参数格式无效')
  }
  if (!bearerToken(request)) {
    return lockedCard(symbol, market, period, requestId, request.method)
  }
  await authenticate(request, env)

  const klines = await fetchMarketKlines({
    symbol,
    market,
    period,
    instrument: instrument as 'spot' | 'perp',
    limit,
  })
  if (klines.items.length < 30) throw new HttpError(422, 'K 线数据不足')
  const last = klines.items.at(-1) as Kline
  const first = klines.items.at(-21) ?? klines.items[0] as Kline
  const snapshot = {
    symbol,
    market,
    period,
    instrument,
    last_close: last.close,
    change_20_bars_pct: ((last.close - first.close) / first.close) * 100,
    ma5: sma(klines.items, 5),
    ma20: sma(klines.items, 20),
    ma60: sma(klines.items, 60),
    rsi14: rsi(klines.items),
    volatility_20_bars_pct: volatility(klines.items),
    recent_high: Math.max(...klines.items.slice(-20).map((item) => item.high)),
    recent_low: Math.min(...klines.items.slice(-20).map((item) => item.low)),
    data_source: klines.source,
    data_as_of: last.ts,
  }
  const ai = await invokeAi(env, {
    system:
      '你是专业市场技术分析师。只依据给定结构化行情输出 JSON；语言简练，不添加免责声明、风险提示、营销话术或固定结尾。',
    prompt: `${JSON.stringify(snapshot)}
输出严格 JSON：
{"score":-100到100整数,"confidence":0到1,"rationale":"2到4句技术结构分析","key_levels":[支撑位,阻力位],"plan_note":"一句执行计划说明"}
不得输出 Markdown。`,
    maxTokens: 650,
    temperature: 0.2,
  })
  const output = parseAiJson(ai.content)
  const score = Math.round(bounded(output.score, -100, 100, 0))
  const confidence = bounded(output.confidence, 0, 1, 0.6)
  const narrative =
    typeof output.rationale === 'string' && output.rationale.trim()
      ? output.rationale.trim()
      : '当前技术结构未形成清晰方向。'
  const levels = keyLevels(output.key_levels, klines.items)
  const planNote =
    typeof output.plan_note === 'string' ? output.plan_note.trim() : narrative
  const direction =
    score >= 20
      ? market === 'crypto' && instrument === 'perp' ? 'open_long' : 'buy'
      : score <= -20
        ? market === 'crypto' && instrument === 'perp' ? 'open_short' : 'sell'
        : 'hold'
  const actionable = direction === 'hold'
    ? null
    : {
        direction,
        actionable: true,
        basis: `技术评分 ${score}`,
        size_note: '按账户风险预算执行',
        hint: planNote,
        disclaimer: '',
      }
  const body = {
    symbol,
    market,
    period,
    generated_at: new Date().toISOString(),
    composite_score: score,
    composite_label: compositeLabel(score),
    composite_confidence: confidence,
    agent_scores: [{
      name: 'technical',
      score,
      confidence,
      rationale: narrative,
      key_levels: levels,
    }],
    contradiction: null,
    narrative,
    chan_signals: [],
    actionable,
    trading_plan: tradingPlan(score, last.close, levels, planNote),
    event_risk: null,
    disclaimer: '',
    cached: false,
    token_usage: ai.token_usage,
    llm_mode: 'real',
    llm_provider: ai.provider,
    llm_model: ai.model,
    fallback_used: ai.fallback_used,
    data_source: klines.source,
    data_as_of: last.ts,
    locked: false,
  }
  const response = jsonResponse(body, 200, requestId, request.method)
  response.headers.set('cache-control', 'private, max-age=300')
  return response
}

function intentFor(question: string) {
  if (/空头|轧空|挤空/u.test(question)) return 'short_crowding'
  if (/多头|拥挤/u.test(question)) return 'long_crowding'
  if (/杠杆|持仓|OI/iu.test(question)) return 'leverage_buildup'
  if (/费率|funding/iu.test(question)) return 'funding_extreme'
  return 'overall'
}

function factor(
  value: Record<string, number>,
  window: string,
  asof: string,
  text: string | null = null,
) {
  return { value, window, asof, text }
}

async function diagnoseStructure(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await authenticate(request, env)
  const body = await readJsonObject(request)
  const rawSymbol = typeof body.symbol === 'string' ? body.symbol.trim().toUpperCase() : ''
  const question = typeof body.question === 'string' ? body.question.trim() : ''
  if (!/^[A-Z0-9]{2,20}(?:USDT)?$/u.test(rawSymbol) || question.length < 2) {
    throw new HttpError(400, 'symbol 或 question 格式无效')
  }
  const symbol = rawSymbol.endsWith('USDT') ? rawSymbol : `${rawSymbol}USDT`
  const context = await fetchCryptoAiContext(symbol)
  const intent = intentFor(question)
  const snapshot = {
    symbol,
    generated_at: new Date().toISOString(),
    account_long_short:
      context.account_long_short_ratio === null
        ? null
        : factor(
            { latest: context.account_long_short_ratio },
            'latest',
            context.as_of,
          ),
    position_long_short: null,
    taker_flow: null,
    open_interest: factor({
      latest_usd: context.open_interest_usd,
      change_24h_pct: context.oi_change_pct_24h ?? 0,
    }, '24h', context.as_of),
    funding_rate:
      context.funding_rate === null
        ? null
        : factor({ latest: context.funding_rate }, 'latest', context.as_of),
    basis: factor({ latest_pct: context.basis_pct }, 'latest', context.as_of),
    sentiment: null,
    funding_predicted: null,
    funding_zscore: null,
    oi_volume_ratio: null,
    global_long_short: null,
    depth: null,
  }
  const ai = await invokeAi(env, {
    system:
      '你是面向专业交易员的市场结构分析师。根据输入指标给出直接、精炼的结构判断。只输出 JSON，不添加免责声明、固定风险提示或营销话术。',
    prompt: `${JSON.stringify({ question, intent, snapshot })}
输出严格 JSON：
{"conclusion":"3到5句结构结论","factor_findings":[{"factor":"account_long_short|open_interest|funding_rate|basis","state":"偏多|偏空|中性|极端|升温|降温","detail":"一句依据","window":"latest或24h"}]}
只评价存在的数据，不补造缺失指标，不输出 Markdown。`,
    maxTokens: 750,
    temperature: 0.2,
  })
  const output = parseAiJson(ai.content)
  const conclusion =
    typeof output.conclusion === 'string' && output.conclusion.trim()
      ? output.conclusion.trim()
      : '现有数据不足以形成清晰的结构结论。'
  const allowed = new Set([
    'account_long_short',
    'open_interest',
    'funding_rate',
    'basis',
  ])
  const findings = Array.isArray(output.factor_findings)
    ? output.factor_findings.flatMap((item) => {
        if (typeof item !== 'object' || item === null) return []
        const row = item as Record<string, unknown>
        if (typeof row.factor !== 'string' || !allowed.has(row.factor)) return []
        return [{
          factor: row.factor,
          state: typeof row.state === 'string' ? row.state : '中性',
          detail: typeof row.detail === 'string' ? row.detail : '',
          window: typeof row.window === 'string' ? row.window : 'latest',
        }]
      })
    : []
  return jsonResponse({
    conclusion,
    factor_findings: findings,
    intent,
    unsupported_note: null,
    snapshot,
    ai_provider: ai.provider,
    ai_model: ai.model,
    fallback_used: ai.fallback_used,
  }, 200, requestId, request.method)
}

export async function handleAnalysisRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (
    path === '/api/v1/analysis/decision-card' &&
    request.method === 'GET'
  ) {
    return decisionCard(request, env, requestId)
  }
  if (
    path === '/api/v1/structure/diagnose' &&
    request.method === 'POST'
  ) {
    return diagnoseStructure(request, env, requestId)
  }
  if (
    path === '/api/v1/analysis/strategy-signals' &&
    request.method === 'GET'
  ) {
    return strategySignals(request, env, requestId)
  }
  if (
    path === '/api/v1/analysis/strategy-recommend' &&
    request.method === 'GET'
  ) {
    return strategyRecommend(request, requestId)
  }
  return path.startsWith('/api/v1/analysis/') ||
    path.startsWith('/api/v1/structure/')
    ? jsonResponse(
        { detail: 'Route not found' },
        404,
        requestId,
        request.method,
      )
    : null
}
