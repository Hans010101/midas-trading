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
