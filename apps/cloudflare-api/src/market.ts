import { HttpError, jsonResponse } from './http'

const MARKETS = new Set(['cn', 'us', 'hk', 'crypto'])
const PERIODS = new Set(['1m', '5m', '15m', '30m', '1h', '1d', '1w'])

type Kline = Readonly<{
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number | null
}>

type SymbolMeta = Readonly<{
  symbol: string
  market: string
  name: string
  name_en?: string
}>

const SYMBOLS: readonly SymbolMeta[] = [
  { symbol: '600519', market: 'cn', name: '贵州茅台', name_en: 'Kweichow Moutai' },
  { symbol: '601318', market: 'cn', name: '中国平安', name_en: 'Ping An' },
  { symbol: '600036', market: 'cn', name: '招商银行', name_en: 'China Merchants Bank' },
  { symbol: '000001', market: 'cn', name: '平安银行', name_en: 'Ping An Bank' },
  { symbol: '000858', market: 'cn', name: '五粮液', name_en: 'Wuliangye' },
  { symbol: '300750', market: 'cn', name: '宁德时代', name_en: 'CATL' },
  { symbol: 'AAPL', market: 'us', name: '苹果', name_en: 'Apple' },
  { symbol: 'MSFT', market: 'us', name: '微软', name_en: 'Microsoft' },
  { symbol: 'NVDA', market: 'us', name: '英伟达', name_en: 'NVIDIA' },
  { symbol: 'GOOGL', market: 'us', name: '谷歌', name_en: 'Alphabet' },
  { symbol: 'AMZN', market: 'us', name: '亚马逊', name_en: 'Amazon' },
  { symbol: 'TSLA', market: 'us', name: '特斯拉', name_en: 'Tesla' },
  { symbol: 'META', market: 'us', name: 'Meta', name_en: 'Meta Platforms' },
  { symbol: '00700', market: 'hk', name: '腾讯控股', name_en: 'Tencent' },
  { symbol: '09988', market: 'hk', name: '阿里巴巴-W', name_en: 'Alibaba' },
  { symbol: '03690', market: 'hk', name: '美团-W', name_en: 'Meituan' },
  { symbol: '01810', market: 'hk', name: '小米集团-W', name_en: 'Xiaomi' },
  { symbol: '00941', market: 'hk', name: '中国移动', name_en: 'China Mobile' },
  { symbol: '01211', market: 'hk', name: '比亚迪股份', name_en: 'BYD' },
  { symbol: 'BTC/USDT', market: 'crypto', name: '比特币', name_en: 'Bitcoin' },
  { symbol: 'ETH/USDT', market: 'crypto', name: '以太坊', name_en: 'Ethereum' },
  { symbol: 'SOL/USDT', market: 'crypto', name: 'Solana', name_en: 'Solana' },
  { symbol: 'BNB/USDT', market: 'crypto', name: 'BNB', name_en: 'BNB' },
  { symbol: 'XRP/USDT', market: 'crypto', name: '瑞波', name_en: 'XRP' },
  { symbol: 'TRX/USDT', market: 'crypto', name: '波场', name_en: 'TRON' },
  { symbol: 'DOGE/USDT', market: 'crypto', name: '狗狗币', name_en: 'Dogecoin' },
]

function yahooSymbol(symbol: string, market: string): string {
  const normalized = symbol.trim().toUpperCase()
  if (market === 'us') return normalized
  if (market === 'hk') {
    return `${normalized.replace(/^0+/u, '').padStart(4, '0')}.HK`
  }
  if (market === 'cn') {
    return `${normalized}.${normalized.startsWith('6') ? 'SS' : 'SZ'}`
  }
  throw new HttpError(400, '市场不支持 Yahoo K 线')
}

function yahooPeriod(period: string): { interval: string; range: string } {
  switch (period) {
    case '1m':
      return { interval: '1m', range: '5d' }
    case '5m':
      return { interval: '5m', range: '1mo' }
    case '15m':
      return { interval: '15m', range: '1mo' }
    case '30m':
      return { interval: '30m', range: '1mo' }
    case '1h':
      return { interval: '1h', range: '3mo' }
    case '1d':
      return { interval: '1d', range: '2y' }
    case '1w':
      return { interval: '1wk', range: '10y' }
    default:
      throw new HttpError(400, '周期不受支持')
  }
}

function validOhlc(
  open: unknown,
  high: unknown,
  low: unknown,
  close: unknown,
): open is number {
  return (
    typeof open === 'number' &&
    typeof high === 'number' &&
    typeof low === 'number' &&
    typeof close === 'number' &&
    Number.isFinite(open) &&
    Number.isFinite(high) &&
    Number.isFinite(low) &&
    Number.isFinite(close) &&
    open > 0 &&
    high >= Math.max(open, close) &&
    low > 0 &&
    low <= Math.min(open, close)
  )
}

async function fetchYahooKlines(
  symbol: string,
  market: string,
  period: string,
  limit: number,
): Promise<Kline[]> {
  const upstreamSymbol = yahooSymbol(symbol, market)
  const { interval, range } = yahooPeriod(period)
  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(upstreamSymbol)}`,
  )
  url.searchParams.set('interval', interval)
  url.searchParams.set('range', range)
  url.searchParams.set('events', 'history')
  const response = await fetch(url, {
    headers: { 'user-agent': 'Midas-Trading-Cloudflare/1.0' },
    signal: AbortSignal.timeout(10_000),
  })
  if (response.status === 404) throw new HttpError(404, '标的不存在')
  if (!response.ok) {
    throw new HttpError(503, `Yahoo 行情暂不可用（HTTP ${response.status}）`)
  }
  const payload = (await response.json()) as {
    chart?: {
      error?: { description?: string } | null
      result?: Array<{
        timestamp?: number[]
        indicators?: {
          quote?: Array<{
            open?: Array<number | null>
            high?: Array<number | null>
            low?: Array<number | null>
            close?: Array<number | null>
            volume?: Array<number | null>
          }>
        }
      }>
    }
  }
  if (payload.chart?.error) {
    throw new HttpError(404, payload.chart.error.description ?? '标的不存在')
  }
  const chart = payload.chart?.result?.[0]
  const quote = chart?.indicators?.quote?.[0]
  const timestamps = chart?.timestamp ?? []
  const items = timestamps.flatMap((timestamp, index) => {
    const open = quote?.open?.[index]
    const high = quote?.high?.[index]
    const low = quote?.low?.[index]
    const close = quote?.close?.[index]
    if (!validOhlc(open, high, low, close)) return []
    const volume = quote?.volume?.[index]
    return [{
      ts: new Date(timestamp * 1_000).toISOString(),
      open,
      high: high as number,
      low: low as number,
      close: close as number,
      volume:
        typeof volume === 'number' && Number.isFinite(volume) && volume >= 0
          ? volume
          : 0,
      amount: null,
    }]
  })
  return items.slice(-limit)
}

function krakenPair(symbol: string): string {
  const base = symbol.split('/')[0]?.toUpperCase()
  if (!base) throw new HttpError(400, '数字资产标的格式无效')
  const krakenBase = base === 'BTC' ? 'XBT' : base === 'DOGE' ? 'XDG' : base
  return `${krakenBase}USD`
}

function krakenInterval(period: string): number {
  const intervals: Readonly<Record<string, number>> = {
    '1m': 1,
    '5m': 5,
    '15m': 15,
    '30m': 30,
    '1h': 60,
    '1d': 1_440,
    '1w': 10_080,
  }
  const interval = intervals[period]
  if (!interval) throw new HttpError(400, '周期不受支持')
  return interval
}

async function fetchKrakenKlines(
  symbol: string,
  period: string,
  limit: number,
): Promise<Kline[]> {
  const url = new URL('https://api.kraken.com/0/public/OHLC')
  url.searchParams.set('pair', krakenPair(symbol))
  url.searchParams.set('interval', String(krakenInterval(period)))
  const response = await fetch(url, {
    headers: { accept: 'application/json' },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) {
    throw new HttpError(503, `Kraken 行情暂不可用（HTTP ${response.status}）`)
  }
  const payload = (await response.json()) as {
    error?: string[]
    result?: Record<string, unknown>
  }
  if (payload.error && payload.error.length > 0) {
    const notFound = payload.error.some((error) =>
      error.toLowerCase().includes('unknown asset pair'),
    )
    throw new HttpError(notFound ? 404 : 503, payload.error.join(', '))
  }
  const entry = Object.entries(payload.result ?? {}).find(
    ([key, value]) => key !== 'last' && Array.isArray(value),
  )
  const rawRows = (entry?.[1] ?? []) as unknown[][]
  const items = rawRows.flatMap((row) => {
    const timestamp = Number(row[0])
    const open = Number(row[1])
    const high = Number(row[2])
    const low = Number(row[3])
    const close = Number(row[4])
    const volume = Number(row[6])
    if (
      !Number.isFinite(timestamp) ||
      !validOhlc(open, high, low, close)
    ) {
      return []
    }
    return [{
      ts: new Date(timestamp * 1_000).toISOString(),
      open,
      high,
      low,
      close,
      volume: Number.isFinite(volume) && volume >= 0 ? volume : 0,
      amount: null,
    }]
  })
  return items.slice(-limit)
}

async function getKlines(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  void env
  const url = new URL(request.url)
  const symbol = url.searchParams.get('symbol')?.trim() ?? ''
  const market = url.searchParams.get('market') ?? ''
  const period = url.searchParams.get('period') ?? '1d'
  const instrument = url.searchParams.get('instrument') ?? 'spot'
  const limit = Number(url.searchParams.get('limit') ?? '500')
  if (!symbol || !MARKETS.has(market) || !PERIODS.has(period)) {
    throw new HttpError(400, 'symbol、market 或 period 格式无效')
  }
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 5_000) {
    throw new HttpError(400, 'limit 必须在 1 到 5000 之间')
  }
  if (instrument === 'perp' && market !== 'crypto') {
    throw new HttpError(400, 'perp 仅支持数字资产市场')
  }
  if (instrument !== 'spot' && instrument !== 'perp') {
    throw new HttpError(400, 'instrument 仅支持 spot 或 perp')
  }
  const items =
    market === 'crypto'
      ? await fetchKrakenKlines(symbol, period, limit)
      : await fetchYahooKlines(symbol, market, period, limit)
  if (items.length === 0) throw new HttpError(404, '未找到 K 线数据')
  const response = jsonResponse(
    { symbol, market, period, items },
    200,
    requestId,
    request.method,
  )
  response.headers.set('cache-control', 'public, max-age=15, s-maxage=60')
  return response
}

function searchSymbols(
  request: Request,
  requestId: string,
): Response {
  const url = new URL(request.url)
  const query = (url.searchParams.get('q') ?? '').trim().toLowerCase()
  const market = url.searchParams.get('market')
  const limit = Number(url.searchParams.get('limit') ?? '50')
  if (!query || query.length > 64) throw new HttpError(400, 'q 格式无效')
  if (market && !MARKETS.has(market)) throw new HttpError(400, 'market 格式无效')
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 200) {
    throw new HttpError(400, 'limit 格式无效')
  }
  const updatedAt = new Date().toISOString()
  const items = SYMBOLS.filter(
    (item) =>
      (!market || item.market === market) &&
      [item.symbol, item.name, item.name_en ?? ''].some((value) =>
        value.toLowerCase().includes(query),
      ),
  )
    .slice(0, limit)
    .map((item) => ({
      ...item,
      listed_date: null,
      is_active: true,
      updated_at: updatedAt,
    }))
  return jsonResponse(items, 200, requestId, request.method)
}

export async function handleMarketRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (path === '/api/v1/market/kline' && request.method === 'GET') {
    return getKlines(request, env, requestId)
  }
  if (path === '/api/v1/market/symbols' && request.method === 'GET') {
    return searchSymbols(request, requestId)
  }
  return path.startsWith('/api/v1/market/')
    ? jsonResponse(
        { detail: 'Route not found' },
        404,
        requestId,
        request.method,
      )
    : null
}
