import { authenticate } from './auth'
import { HttpError, jsonResponse, readJsonObject } from './http'

const OPERATORS = new Set(['gt', 'gte', 'lt', 'lte'])
const MARKETS = new Set(['cn', 'us', 'hk', 'crypto'])
const MAX_RULES = 50

const INDICATORS = [
  ['price', '最新价', 'price', ['cn', 'us', 'hk', 'crypto'], true, true, null],
  ['price_change_pct', '涨跌幅 %', 'price', ['cn', 'us', 'hk', 'crypto'], true, true, '%'],
  ['volume', '成交量', 'volume', ['cn', 'us', 'hk', 'crypto'], true, true, null],
  ['ma_5', 'MA5', 'technical', ['cn', 'us', 'hk', 'crypto'], true, true, null],
  ['ma_20', 'MA20', 'technical', ['cn', 'us', 'hk', 'crypto'], true, true, null],
  ['ma_60', 'MA60', 'technical', ['cn', 'us', 'hk', 'crypto'], true, true, null],
  ['macd_hist', 'MACD 柱', 'technical', ['cn', 'us', 'hk', 'crypto'], true, true, null],
  ['rsi_14', 'RSI(14)', 'technical', ['cn', 'us', 'hk', 'crypto'], true, true, null],
  ['boll_pctb', '布林 %B', 'technical', ['cn', 'us', 'hk', 'crypto'], true, true, '%'],
  ['funding_rate', '资金费率', 'crypto_deriv', ['crypto'], true, false, '%'],
  ['open_interest_usd', '合约持仓额', 'crypto_deriv', ['crypto'], true, false, 'USD'],
  ['long_short_ratio', '账户多空比', 'crypto_deriv', ['crypto'], true, false, null],
  ['basis_pct', '合约基差', 'crypto_deriv', ['crypto'], true, false, '%'],
] as const

const META: ReadonlyMap<string, (typeof INDICATORS)[number]> = new Map(
  INDICATORS.map((item) => [item[0], item]),
)

type RuleRow = Readonly<{
  id: number
  market: string
  symbol: string | null
  indicator: string
  operator: string
  threshold: string
  timeframe: string | null
  enabled: number
  cooldown_sec: number
}>

function serialize(row: RuleRow) {
  return { ...row, enabled: row.enabled === 1 }
}

async function list(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const rows = await env.DB
    .prepare(
      `SELECT id, market, symbol, indicator, operator, threshold,
              timeframe, enabled, cooldown_sec
       FROM alert_rules WHERE user_id = ? ORDER BY created_at ASC`,
    )
    .bind(user.id)
    .all<RuleRow>()
  return jsonResponse(rows.results.map(serialize), 200, requestId, request.method)
}

function requiredString(body: Readonly<Record<string, unknown>>, key: string): string {
  const value = body[key]
  if (typeof value !== 'string' || !value.trim()) {
    throw new HttpError(400, `${key} 格式无效`)
  }
  return value.trim()
}

async function create(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const market = requiredString(body, 'market')
  const indicator = requiredString(body, 'indicator')
  const operator = requiredString(body, 'operator')
  const definition = META.get(indicator)
  if (!MARKETS.has(market) || !definition || !definition[3].includes(market as never)) {
    throw new HttpError(400, '指标或市场不受支持')
  }
  if (!OPERATORS.has(operator)) throw new HttpError(400, 'operator 不受支持')
  const threshold = body.threshold
  if (typeof threshold !== 'number' || !Number.isFinite(threshold)) {
    throw new HttpError(400, 'threshold 必须是有限数值')
  }
  const symbol =
    typeof body.symbol === 'string' && body.symbol.trim()
      ? body.symbol.trim().toUpperCase()
      : null
  if (definition[4] && !symbol) throw new HttpError(400, '该指标必须指定标的')
  const count = await env.DB
    .prepare('SELECT COUNT(*) AS count FROM alert_rules WHERE user_id = ?')
    .bind(user.id)
    .first<{ count: number }>()
  if ((count?.count ?? 0) >= MAX_RULES) throw new HttpError(400, '告警规则数量已达上限')
  const now = Date.now()
  const result = await env.DB
    .prepare(
      `INSERT INTO alert_rules
        (user_id, market, symbol, indicator, operator, threshold,
         timeframe, cooldown_sec, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, 300, ?, ?)`,
    )
    .bind(
      user.id,
      market,
      definition[4] ? symbol : null,
      indicator,
      operator,
      String(threshold),
      definition[5] && typeof body.timeframe === 'string' ? body.timeframe : null,
      now,
      now,
    )
    .run()
  const row = await env.DB
    .prepare(
      `SELECT id, market, symbol, indicator, operator, threshold,
              timeframe, enabled, cooldown_sec
       FROM alert_rules WHERE id = ? AND user_id = ?`,
    )
    .bind(result.meta.last_row_id, user.id)
    .first<RuleRow>()
  return jsonResponse(serialize(row!), 201, requestId, request.method)
}

async function patchRule(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  if (typeof body.enabled !== 'boolean') throw new HttpError(400, 'enabled 必须是布尔值')
  const result = await env.DB
    .prepare('UPDATE alert_rules SET enabled = ?, updated_at = ? WHERE id = ? AND user_id = ?')
    .bind(body.enabled ? 1 : 0, Date.now(), id, user.id)
    .run()
  if (result.meta.changes !== 1) throw new HttpError(404, '规则不存在或无权访问')
  const row = await env.DB
    .prepare(
      `SELECT id, market, symbol, indicator, operator, threshold,
              timeframe, enabled, cooldown_sec
       FROM alert_rules WHERE id = ? AND user_id = ?`,
    )
    .bind(id, user.id)
    .first<RuleRow>()
  return jsonResponse(serialize(row!), 200, requestId, request.method)
}

async function deleteRule(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  const { user } = await authenticate(request, env)
  const result = await env.DB
    .prepare('DELETE FROM alert_rules WHERE id = ? AND user_id = ?')
    .bind(id, user.id)
    .run()
  if (result.meta.changes !== 1) throw new HttpError(404, '规则不存在或无权访问')
  return jsonResponse({}, 204, requestId, request.method)
}

async function applyRecommended(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const recommendations = [
    ['us', 'NVDA', 'rsi_14', 'gt', '75', '1d'],
    ['us', 'NVDA', 'rsi_14', 'lt', '25', '1d'],
    ['cn', '600519', 'rsi_14', 'gt', '75', '1d'],
    ['cn', '600519', 'rsi_14', 'lt', '25', '1d'],
    ['crypto', 'BTC/USDT', 'rsi_14', 'gt', '80', '1d'],
    ['crypto', 'BTC/USDT', 'rsi_14', 'lt', '20', '1d'],
  ] as const
  const existing = await env.DB
    .prepare('SELECT market, symbol, indicator, operator, threshold FROM alert_rules WHERE user_id = ?')
    .bind(user.id)
    .all<Pick<RuleRow, 'market' | 'symbol' | 'indicator' | 'operator' | 'threshold'>>()
  const keys = new Set(
    existing.results.map((row) =>
      [row.market, row.symbol, row.indicator, row.operator, row.threshold].join('|'),
    ),
  )
  const now = Date.now()
  const statements: D1PreparedStatement[] = []
  let skipped = 0
  for (const item of recommendations) {
    const key = item.join('|')
    if (keys.has(key) || existing.results.length + statements.length >= MAX_RULES) {
      skipped += 1
      continue
    }
    statements.push(
      env.DB
        .prepare(
          `INSERT INTO alert_rules
            (user_id, market, symbol, indicator, operator, threshold,
             timeframe, cooldown_sec, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 300, ?, ?)`,
        )
        .bind(user.id, ...item, now, now),
    )
  }
  if (statements.length > 0) await env.DB.batch(statements)
  return jsonResponse(
    { created: statements.length, skipped },
    200,
    requestId,
    request.method,
  )
}

export async function handleAlertRulesRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (!path.startsWith('/api/v1/alert-rules')) return null
  if (path === '/api/v1/alert-rules/indicators' && request.method === 'GET') {
    await authenticate(request, env)
    return jsonResponse(
      INDICATORS.map(([key, label, category, markets, requiresSymbol, needsTimeframe, unit]) => ({
        key,
        label,
        category,
        markets,
        requires_symbol: requiresSymbol,
        needs_timeframe: needsTimeframe,
        unit,
      })),
      200,
      requestId,
      request.method,
    )
  }
  if (path === '/api/v1/alert-rules/apply-recommended' && request.method === 'POST') {
    return applyRecommended(request, env, requestId)
  }
  if (path === '/api/v1/alert-rules') {
    if (request.method === 'GET') return list(request, env, requestId)
    if (request.method === 'POST') return create(request, env, requestId)
  }
  const match = path.match(/^\/api\/v1\/alert-rules\/(\d+)$/u)
  if (match?.[1]) {
    const id = Number(match[1])
    if (request.method === 'PATCH') return patchRule(request, env, requestId, id)
    if (request.method === 'DELETE') return deleteRule(request, env, requestId, id)
  }
  return jsonResponse({ detail: 'Route not found' }, 404, requestId, request.method)
}
