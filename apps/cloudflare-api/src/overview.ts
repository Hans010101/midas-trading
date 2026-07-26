import { HttpError, jsonResponse } from './http'

type QuoteConfig = Readonly<{
  symbol: string
  name: string
  market: string
  category: string
  unit: 'point' | 'price' | 'rate' | 'yield_pct'
}>

type OverviewRow = Readonly<{
  symbol: string
  name: string
  market: string
  category: string
  unit: string
  quoted_at: number
  last_point: number
  prev_close: number
  change_point: number
  change_pct: number
}>

const YAHOO_QUOTES: readonly QuoteConfig[] = [
  { symbol: '^GSPC', name: '标普500', market: 'us', category: 'index', unit: 'point' },
  { symbol: '^IXIC', name: '纳斯达克', market: 'us', category: 'index', unit: 'point' },
  { symbol: '^DJI', name: '道琼斯', market: 'us', category: 'index', unit: 'point' },
  { symbol: '^N225', name: '日经225', market: 'jp', category: 'index', unit: 'point' },
  { symbol: '^HSI', name: '恒生指数', market: 'hk', category: 'index', unit: 'point' },
  { symbol: '^HSCE', name: '恒生国企指数', market: 'hk', category: 'index', unit: 'point' },
  { symbol: '000001.SS', name: '上证指数', market: 'cn', category: 'index', unit: 'point' },
  { symbol: '^GDAXI', name: '德国DAX', market: 'de', category: 'index', unit: 'point' },
  { symbol: '^FTSE', name: '英国富时100', market: 'uk', category: 'index', unit: 'point' },
  { symbol: '^KS11', name: '韩国KOSPI', market: 'kr', category: 'index', unit: 'point' },
  { symbol: '^STI', name: '新加坡STI', market: 'sg', category: 'index', unit: 'point' },
  { symbol: '^FCHI', name: '法国CAC40', market: 'fr', category: 'index', unit: 'point' },
  { symbol: '^AXJO', name: '澳洲ASX200', market: 'au', category: 'index', unit: 'point' },
  { symbol: '^NSEI', name: '印度NIFTY', market: 'in', category: 'index', unit: 'point' },
  { symbol: '^TWII', name: '台湾加权', market: 'tw', category: 'index', unit: 'point' },
  { symbol: '^BVSP', name: '巴西BOVESPA', market: 'br', category: 'index', unit: 'point' },
  { symbol: '^GSPTSE', name: '加拿大TSX', market: 'ca', category: 'index', unit: 'point' },
  { symbol: '^SSMI', name: '瑞士SMI', market: 'ch', category: 'index', unit: 'point' },
  { symbol: '^JKSE', name: '印尼综合', market: 'id', category: 'index', unit: 'point' },
  { symbol: '^STOXX50E', name: '欧洲STOXX50', market: 'eu', category: 'index', unit: 'point' },
  { symbol: '^RUT', name: '罗素2000', market: 'us', category: 'index', unit: 'point' },
  { symbol: '000300.SS', name: '沪深300', market: 'cn', category: 'index', unit: 'point' },
  { symbol: '399001.SZ', name: '深证成指', market: 'cn', category: 'index', unit: 'point' },
  { symbol: 'GC=F', name: '黄金', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'SI=F', name: '白银', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'CL=F', name: 'WTI原油', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'BZ=F', name: '布伦特原油', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'HG=F', name: '铜', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'NG=F', name: '天然气', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'ZS=F', name: '大豆', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'ZC=F', name: '玉米', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'ZW=F', name: '小麦', market: 'global', category: 'commodity', unit: 'price' },
  { symbol: 'DX-Y.NYB', name: '美元指数', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: 'JPY=X', name: '美元日元', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: 'EURUSD=X', name: '欧元美元', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: 'CNY=X', name: '美元人民币', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: 'GBPUSD=X', name: '英镑美元', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: 'AUDUSD=X', name: '澳元美元', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: 'USDCAD=X', name: '美元加元', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: 'USDHKD=X', name: '美元港币', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: 'USDKRW=X', name: '美元韩元', market: 'fx', category: 'forex', unit: 'rate' },
  { symbol: '^TNX', name: '美债10年', market: 'us', category: 'bond', unit: 'yield_pct' },
  { symbol: '^TYX', name: '美债30年', market: 'us', category: 'bond', unit: 'yield_pct' },
  { symbol: '^FVX', name: '美债5年', market: 'us', category: 'bond', unit: 'yield_pct' },
  { symbol: '2YY=F', name: '美债2年', market: 'us', category: 'bond', unit: 'yield_pct' },
  { symbol: '^VIX', name: 'VIX恐慌指数', market: 'global', category: 'sentiment', unit: 'point' },
  { symbol: '^VXN', name: '纳指VIX', market: 'global', category: 'sentiment', unit: 'point' },
  { symbol: '^OVX', name: '原油波动率', market: 'global', category: 'sentiment', unit: 'point' },
]

const CRYPTO_QUOTES = [
  ['XXBTZUSD', 'BTC/USDT', '比特币'],
  ['XETHZUSD', 'ETH/USDT', '以太坊'],
  ['SOLUSD', 'SOL/USDT', 'Solana'],
  ['BNBUSD', 'BNB/USDT', 'BNB'],
  ['XXRPZUSD', 'XRP/USDT', '瑞波XRP'],
  ['TRXUSD', 'TRX/USDT', '波场TRX'],
  ['XDGUSD', 'DOGE/USDT', '狗狗币'],
] as const

const CATEGORY_ORDER = ['index', 'commodity', 'forex', 'bond', 'sentiment', 'crypto'] as const
const CATEGORY_LABELS: Readonly<Record<string, string>> = {
  index: '环球指数',
  commodity: '商品期货',
  forex: '外汇',
  bond: '债券收益率',
  sentiment: '市场情绪',
  crypto: '加密货币',
}
const SYMBOL_ORDER = new Map(
  [
    ...YAHOO_QUOTES.map(({ symbol }) => symbol),
    ...CRYPTO_QUOTES.map(([, symbol]) => symbol),
  ].map((symbol, index) => [symbol, index]),
)

function finitePositive(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? value
    : null
}

async function fetchYahooQuote(config: QuoteConfig): Promise<OverviewRow | null> {
  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(config.symbol)}`,
  )
  url.searchParams.set('range', '5d')
  url.searchParams.set('interval', '1d')
  const response = await fetch(url, {
    headers: { 'user-agent': 'Midas-Trading-Cloudflare/1.0' },
    signal: AbortSignal.timeout(8_000),
  })
  if (!response.ok) throw new Error(`Yahoo ${config.symbol}: HTTP ${response.status}`)
  const payload = (await response.json()) as {
    chart?: {
      result?: Array<{
        meta?: {
          regularMarketPrice?: number
          chartPreviousClose?: number
          previousClose?: number
          regularMarketTime?: number
        }
        timestamp?: number[]
        indicators?: { quote?: Array<{ close?: Array<number | null> }> }
      }>
    }
  }
  const chart = payload.chart?.result?.[0]
  const closes = chart?.indicators?.quote?.[0]?.close?.filter(
    (value): value is number => typeof value === 'number' && Number.isFinite(value),
  ) ?? []
  const last = finitePositive(chart?.meta?.regularMarketPrice) ??
    finitePositive(closes.at(-1))
  const previous = finitePositive(chart?.meta?.chartPreviousClose) ??
    finitePositive(chart?.meta?.previousClose) ??
    finitePositive(closes.at(-2))
  if (last === null || previous === null) return null
  const change = last - previous
  const quotedAt =
    (chart?.meta?.regularMarketTime ?? chart?.timestamp?.at(-1) ?? Math.floor(Date.now() / 1_000)) *
    1_000
  return {
    ...config,
    quoted_at: quotedAt,
    last_point: last,
    prev_close: previous,
    change_point: change,
    change_pct: (change / previous) * 100,
  }
}

async function fetchCryptoQuotes(): Promise<OverviewRow[]> {
  const url = new URL('https://api.kraken.com/0/public/Ticker')
  url.searchParams.set(
    'pair',
    'XBTUSD,ETHUSD,SOLUSD,BNBUSD,XRPUSD,TRXUSD,DOGEUSD',
  )
  const response = await fetch(url, {
    headers: { accept: 'application/json' },
    signal: AbortSignal.timeout(8_000),
  })
  if (!response.ok) throw new Error(`Kraken: HTTP ${response.status}`)
  const payload = (await response.json()) as {
    error?: string[]
    result?: Record<string, { c?: string[]; o?: string }>
  }
  if (payload.error && payload.error.length > 0) {
    throw new Error(`Kraken: ${payload.error.join(', ')}`)
  }
  return CRYPTO_QUOTES.flatMap(([krakenSymbol, symbol, name]) => {
    const quote = payload.result?.[krakenSymbol]
    const last = Number(quote?.c?.[0])
    const previous = Number(quote?.o)
    const change = last - previous
    const changePct = (change / previous) * 100
    if (
      !Number.isFinite(last) ||
      last <= 0 ||
      !Number.isFinite(previous) ||
      previous <= 0 ||
      !Number.isFinite(changePct)
    ) {
      return []
    }
    return [{
      symbol,
      name,
      market: 'crypto',
      category: 'crypto',
      unit: 'price',
      quoted_at: Date.now(),
      last_point: last,
      prev_close: previous,
      change_point: change,
      change_pct: changePct,
    }]
  })
}

async function mapWithConcurrency<T, R>(
  input: readonly T[],
  concurrency: number,
  operation: (value: T) => Promise<R>,
): Promise<PromiseSettledResult<R>[]> {
  const output: PromiseSettledResult<R>[] = new Array(input.length)
  let cursor = 0
  await Promise.all(
    Array.from({ length: Math.min(concurrency, input.length) }, async () => {
      while (cursor < input.length) {
        const index = cursor
        cursor += 1
        try {
          output[index] = {
            status: 'fulfilled',
            value: await operation(input[index]!),
          }
        } catch (reason) {
          output[index] = { status: 'rejected', reason }
        }
      }
    }),
  )
  return output
}

export async function refreshGlobalOverview(env: Env): Promise<{
  stored: number
  failed: number
}> {
  const yahooResults = await mapWithConcurrency(
    YAHOO_QUOTES,
    6,
    fetchYahooQuote,
  )
  let cryptoRows: OverviewRow[] = []
  let cryptoFailed = 0
  try {
    cryptoRows = await fetchCryptoQuotes()
  } catch (error) {
    cryptoFailed = 1
    console.error(
      JSON.stringify({
        event: 'overview.crypto_refresh_failed',
        error: error instanceof Error ? error.message : String(error),
      }),
    )
  }
  const yahooRows = yahooResults.flatMap((result) =>
    result.status === 'fulfilled' && result.value ? [result.value] : [],
  )
  const rows = [...yahooRows, ...cryptoRows]
  const timestamp = Date.now()
  if (rows.length > 0) {
    await env.DB.batch(
      rows.map((row) =>
        env.DB
          .prepare(
            `INSERT INTO market_overview_quotes
              (symbol, market, name, category, unit, quoted_at, last_point,
               prev_close, change_point, change_pct, source, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(symbol) DO UPDATE SET
               market = excluded.market,
               name = excluded.name,
               category = excluded.category,
               unit = excluded.unit,
               quoted_at = excluded.quoted_at,
               last_point = excluded.last_point,
               prev_close = excluded.prev_close,
               change_point = excluded.change_point,
               change_pct = excluded.change_pct,
               source = excluded.source,
               updated_at = excluded.updated_at`,
          )
          .bind(
            row.symbol,
            row.market,
            row.name,
            row.category,
            row.unit,
            row.quoted_at,
            row.last_point,
            row.prev_close,
            row.change_point,
            row.change_pct,
            row.category === 'crypto' ? 'kraken' : 'yahoo',
            timestamp,
          ),
      ),
    )
  }
  const failed =
    yahooResults.filter((result) => result.status === 'rejected').length +
    cryptoFailed
  console.log(
    JSON.stringify({
      event: 'overview.refresh_complete',
      stored: rows.length,
      failed,
    }),
  )
  return { stored: rows.length, failed }
}

async function readRows(db: D1Database): Promise<OverviewRow[]> {
  const result = await db
    .prepare(
      `SELECT symbol, market, name, category, unit, quoted_at, last_point,
              prev_close, change_point, change_pct
       FROM market_overview_quotes`,
    )
    .all<OverviewRow>()
  return result.results
}

async function globalOverview(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  let rows = await readRows(env.DB)
  if (rows.length === 0) {
    const refresh = await refreshGlobalOverview(env)
    if (refresh.stored === 0) {
      throw new HttpError(503, '全球行情暂不可用，请稍后重试')
    }
    rows = await readRows(env.DB)
  }
  const asOf = Math.max(...rows.map(({ quoted_at }) => quoted_at))
  const groups = CATEGORY_ORDER.flatMap((category) => {
    const items = rows
      .filter((row) => row.category === category)
      .sort(
        (left, right) =>
          (SYMBOL_ORDER.get(left.symbol) ?? 999) -
          (SYMBOL_ORDER.get(right.symbol) ?? 999),
      )
      .map((row) => ({
        market: row.market,
        symbol: row.symbol,
        name: row.name,
        category: row.category,
        unit: row.unit,
        ts: new Date(row.quoted_at).toISOString(),
        last_point: row.last_point,
        prev_close: row.prev_close,
        change_point: row.change_point,
        change_pct: row.change_pct,
      }))
    return items.length > 0
      ? [{ category, label: CATEGORY_LABELS[category], items }]
      : []
  })
  const response = jsonResponse(
    { groups, as_of: new Date(asOf).toISOString() },
    200,
    requestId,
    request.method,
  )
  response.headers.set('cache-control', 'public, max-age=60, s-maxage=300')
  return response
}

export async function handleOverviewRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (path === '/api/v1/overview/global' && request.method === 'GET') {
    return globalOverview(request, env, requestId)
  }
  return path.startsWith('/api/v1/overview/')
    ? jsonResponse(
        { detail: 'Route not found' },
        404,
        requestId,
        request.method,
      )
    : null
}
