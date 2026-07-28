import { HttpError, jsonResponse } from './http'

const FUTURES_TICKERS_URL =
  'https://futures.kraken.com/derivatives/api/v3/tickers'
const FUTURES_ANALYTICS_URL =
  'https://futures.kraken.com/api/charts/v1/analytics'
const SPOT_TICKER_URL = 'https://api.kraken.com/0/public/Ticker'
const BINANCE_FUTURES_URL = 'https://fapi.binance.com'
const OKX_PUBLIC_URL = 'https://www.okx.com/api/v5'
const CACHE_CONTROL = 'public, max-age=15, s-maxage=60'
// Each symbol needs three analytics requests. Keep the Worker invocation below
// Cloudflare Free's 50 external-subrequest ceiling.
const MAX_METRICS_SYMBOLS = 15

type KrakenFutureTicker = Readonly<{
  symbol?: string
  pair?: string
  tag?: string
  last?: number
  lastTime?: string
  markPrice?: number
  indexPrice?: number
  vol24h?: number
  volumeQuote?: number
  openInterest?: number
  fundingRate?: number
  change24h?: number
  high24h?: number
  low24h?: number
}>

type Ticker24h = Readonly<{
  symbol: string
  instrument: 'spot' | 'perp'
  ts: string
  last_price: number
  change_pct_24h: number
  high_24h: number
  low_24h: number
  volume_24h: number
  quote_volume_24h: number
  count_24h: number
}>

function finite(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function numeric(value: unknown, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function cachedJson(
  body: unknown,
  requestId: string,
  method = 'GET',
): Response {
  const response = jsonResponse(body, 200, requestId, method)
  response.headers.set('cache-control', CACHE_CONTROL)
  return response
}

async function fetchJson<T>(url: URL | string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) {
    throw new HttpError(503, `Kraken 行情暂不可用（HTTP ${response.status}）`)
  }
  return (await response.json()) as T
}

async function fetchPublicJson<T>(
  url: URL | string,
  source: string,
): Promise<T> {
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) {
    throw new Error(`${source} HTTP ${response.status}`)
  }
  return (await response.json()) as T
}

type CryptoGlobal = Readonly<{
  total_market_cap_usd: number
  total_volume_24h_usd: number
  btc_dominance: number
  eth_dominance: number
  source: 'coingecko' | 'coinpaprika' | 'coinlore'
}>

async function fetchCoinGeckoGlobal(): Promise<CryptoGlobal> {
  const response = await fetch('https://api.coingecko.com/api/v3/global', {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) {
    throw new Error(`CoinGecko global HTTP ${response.status}`)
  }
  const payload = (await response.json()) as {
    data?: {
      total_market_cap?: { usd?: unknown }
      total_volume?: { usd?: unknown }
      market_cap_percentage?: { btc?: unknown; eth?: unknown }
    }
  }
  const result = {
    total_market_cap_usd: numeric(payload.data?.total_market_cap?.usd),
    total_volume_24h_usd: numeric(payload.data?.total_volume?.usd),
    btc_dominance: numeric(payload.data?.market_cap_percentage?.btc),
    eth_dominance: numeric(payload.data?.market_cap_percentage?.eth),
    source: 'coingecko' as const,
  }
  if (
    result.total_market_cap_usd <= 0 ||
    result.total_volume_24h_usd <= 0 ||
    result.btc_dominance <= 0
  ) {
    throw new Error('CoinGecko global payload incomplete')
  }
  return result
}

async function fetchCoinPaprikaGlobal(): Promise<CryptoGlobal> {
  const [globalResponse, ethResponse] = await Promise.all([
    fetch('https://api.coinpaprika.com/v1/global', {
      headers: {
        accept: 'application/json',
        'user-agent': 'Midas-Trading-Cloudflare/1.0',
      },
      signal: AbortSignal.timeout(10_000),
    }),
    fetch('https://api.coinpaprika.com/v1/tickers/eth-ethereum', {
      headers: {
        accept: 'application/json',
        'user-agent': 'Midas-Trading-Cloudflare/1.0',
      },
      signal: AbortSignal.timeout(10_000),
    }),
  ])
  if (!globalResponse.ok || !ethResponse.ok) {
    throw new Error(
      `CoinPaprika global HTTP ${globalResponse.status}/${ethResponse.status}`,
    )
  }
  const globalPayload = (await globalResponse.json()) as {
    market_cap_usd?: unknown
    volume_24h_usd?: unknown
    bitcoin_dominance_percentage?: unknown
  }
  const ethPayload = (await ethResponse.json()) as {
    quotes?: { USD?: { market_cap?: unknown } }
  }
  const totalMarketCap = numeric(globalPayload.market_cap_usd)
  const ethMarketCap = numeric(ethPayload.quotes?.USD?.market_cap)
  const result = {
    total_market_cap_usd: totalMarketCap,
    total_volume_24h_usd: numeric(globalPayload.volume_24h_usd),
    btc_dominance: numeric(globalPayload.bitcoin_dominance_percentage),
    eth_dominance: totalMarketCap > 0 ? (ethMarketCap / totalMarketCap) * 100 : 0,
    source: 'coinpaprika' as const,
  }
  if (
    result.total_market_cap_usd <= 0 ||
    result.total_volume_24h_usd <= 0 ||
    result.btc_dominance <= 0 ||
    result.eth_dominance <= 0
  ) {
    throw new Error('CoinPaprika global payload incomplete')
  }
  return result
}

async function fetchCryptoGlobal(): Promise<CryptoGlobal> {
  try {
    return await fetchCoinGeckoGlobal()
  } catch {
    try {
      return await fetchCoinPaprikaGlobal()
    } catch {
      const response = await fetch('https://api.coinlore.net/api/global/', {
        headers: {
          accept: 'application/json',
          'user-agent': 'Midas-Trading-Cloudflare/1.0',
        },
        signal: AbortSignal.timeout(10_000),
      })
      if (!response.ok) {
        throw new Error(`CoinLore global HTTP ${response.status}`)
      }
      const payload = (await response.json()) as Array<{
        total_mcap?: unknown
        total_volume?: unknown
        btc_d?: unknown
        eth_d?: unknown
      }>
      const item = payload[0]
      const result = {
        total_market_cap_usd: numeric(item?.total_mcap),
        total_volume_24h_usd: numeric(item?.total_volume),
        btc_dominance: numeric(item?.btc_d),
        eth_dominance: numeric(item?.eth_d),
        source: 'coinlore' as const,
      }
      if (
        result.total_market_cap_usd <= 0 ||
        result.total_volume_24h_usd <= 0 ||
        result.btc_dominance <= 0 ||
        result.eth_dominance <= 0
      ) {
        throw new Error('CoinLore global payload incomplete')
      }
      return result
    }
  }
}

async function fetchFearGreed(): Promise<Readonly<{
  value: number
  classification: string
}>> {
  const response = await fetch('https://api.alternative.me/fng/?limit=1', {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) {
    throw new Error(`Alternative.me FGI HTTP ${response.status}`)
  }
  const payload = (await response.json()) as {
    data?: Array<{ value?: unknown; value_classification?: unknown }>
  }
  const value = numeric(payload.data?.[0]?.value, -1)
  const classification = String(
    payload.data?.[0]?.value_classification ?? '',
  ).trim()
  if (value < 0 || value > 100 || !classification) {
    throw new Error('Alternative.me FGI payload incomplete')
  }
  return { value, classification }
}

function publicBase(pair: string | undefined): string | null {
  const base = pair?.split(':')[0]?.toUpperCase()
  if (!base) return null
  if (base === 'XBT') return 'BTC'
  if (base === 'XDG') return 'DOGE'
  return base
}

function krakenBase(base: string): string {
  if (base === 'BTC') return 'XBT'
  if (base === 'DOGE') return 'DOGE'
  return base
}

function parsePublicSymbol(symbol: string): {
  publicSymbol: string
  futuresSymbol: string
  base: string
} {
  const normalized = symbol.trim().toUpperCase()
  if (!/^[A-Z0-9]{2,20}USDT$/u.test(normalized)) {
    throw new HttpError(400, '数字资产合约标的格式无效')
  }
  const base = normalized.slice(0, -4)
  return {
    publicSymbol: normalized,
    futuresSymbol: `PF_${krakenBase(base)}USD`,
    base,
  }
}

async function futuresTickers(): Promise<KrakenFutureTicker[]> {
  const payload = await fetchJson<{
    result?: string
    tickers?: KrakenFutureTicker[]
  }>(FUTURES_TICKERS_URL)
  if (payload.result !== 'success' || !Array.isArray(payload.tickers)) {
    throw new HttpError(503, 'Kraken 合约行情返回格式异常')
  }
  return payload.tickers
}

function toPerpTicker(ticker: KrakenFutureTicker): Ticker24h | null {
  if (!ticker.symbol?.startsWith('PF_') || !ticker.symbol.endsWith('USD')) {
    return null
  }
  const base = publicBase(ticker.pair)
  const last = finite(ticker.last)
  if (!base || last <= 0) return null
  return {
    symbol: `${base}/USDT`,
    instrument: 'perp',
    ts: ticker.lastTime ?? new Date().toISOString(),
    last_price: last,
    change_pct_24h: finite(ticker.change24h),
    high_24h: finite(ticker.high24h),
    low_24h: finite(ticker.low24h),
    volume_24h: finite(ticker.vol24h),
    quote_volume_24h: finite(ticker.volumeQuote),
    count_24h: 0,
  }
}

async function perpTickerItems(): Promise<Ticker24h[]> {
  return (await futuresTickers()).flatMap((ticker) => {
    const item = toPerpTicker(ticker)
    return item ? [item] : []
  })
}

const SPOT_PAIRS = Object.freeze([
  ['XBTUSD', 'BTC'],
  ['ETHUSD', 'ETH'],
  ['SOLUSD', 'SOL'],
  ['XRPUSD', 'XRP'],
  ['XDGUSD', 'DOGE'],
  ['BNBUSD', 'BNB'],
  ['TRXUSD', 'TRX'],
] as const)

async function spotTickerItems(): Promise<Ticker24h[]> {
  const url = new URL(SPOT_TICKER_URL)
  url.searchParams.set('pair', SPOT_PAIRS.map(([pair]) => pair).join(','))
  const payload = await fetchJson<{
    error?: string[]
    result?: Record<
      string,
      {
        c?: string[]
        v?: string[]
        p?: string[]
        t?: number[]
        l?: string[]
        h?: string[]
        o?: string
      }
    >
  }>(url)
  if (payload.error?.length) {
    throw new HttpError(503, payload.error.join(', '))
  }
  const results = payload.result ?? {}
  const aliases: Readonly<Record<string, readonly string[]>> = {
    BTC: ['XXBTZUSD', 'XBTUSD'],
    ETH: ['XETHZUSD', 'ETHUSD'],
    SOL: ['SOLUSD'],
    XRP: ['XXRPZUSD', 'XRPUSD'],
    DOGE: ['XDGUSD', 'DOGEUSD'],
    BNB: ['BNBUSD'],
    TRX: ['TRXUSD'],
  }
  return SPOT_PAIRS.flatMap(([, base]) => {
    const ticker = aliases[base]
      ?.map((key) => results[key])
      .find((item) => item !== undefined)
    if (!ticker) return []
    const last = numeric(ticker.c?.[0])
    const open = numeric(ticker.o)
    if (last <= 0 || open <= 0) return []
    const volume = numeric(ticker.v?.[1])
    const vwap = numeric(ticker.p?.[1], last)
    return [{
      symbol: `${base}/USDT`,
      instrument: 'spot' as const,
      ts: new Date().toISOString(),
      last_price: last,
      change_pct_24h: ((last - open) / open) * 100,
      high_24h: numeric(ticker.h?.[1]),
      low_24h: numeric(ticker.l?.[1]),
      volume_24h: volume,
      quote_volume_24h: volume * vwap,
      count_24h: numeric(ticker.t?.[1]),
    }]
  })
}

function sortedItems(
  items: Ticker24h[],
  sortBy: string,
  order: string,
  top: number,
): Ticker24h[] {
  const fields: Readonly<Record<string, keyof Ticker24h>> = {
    change_pct_24h: 'change_pct_24h',
    quote_volume_24h: 'quote_volume_24h',
    last_price: 'last_price',
  }
  const field = fields[sortBy]
  if (!field) throw new HttpError(400, 'sort_by 格式无效')
  if (order !== 'asc' && order !== 'desc') {
    throw new HttpError(400, 'order 格式无效')
  }
  const direction = order === 'asc' ? 1 : -1
  return [...items]
    .sort((left, right) => {
      const a = left[field]
      const b = right[field]
      return (Number(a) - Number(b)) * direction
    })
    .slice(0, top)
}

async function analytics(
  futuresSymbol: string,
  kind: 'funding' | 'open-interest' | 'long-short-ratio',
  hours = 168,
): Promise<{
  timestamp?: number[]
  data?: unknown
}> {
  const url = new URL(
    `${FUTURES_ANALYTICS_URL}/${encodeURIComponent(futuresSymbol)}/${kind}`,
  )
  url.searchParams.set('since', String(Math.floor(Date.now() / 1_000) - hours * 3_600))
  url.searchParams.set('interval', '3600')
  const payload = await fetchJson<{
    result?: { timestamp?: number[]; data?: unknown }
  }>(url)
  return payload.result ?? {}
}

function timestampsToIso(values: number[] | undefined): string[] {
  return (values ?? []).map((timestamp) =>
    new Date(timestamp > 10_000_000_000 ? timestamp : timestamp * 1_000).toISOString(),
  )
}

function closeValue(row: unknown): number {
  return Array.isArray(row) ? numeric(row[3]) : numeric(row)
}

async function metricsItem(symbol: string): Promise<{
  symbol: string
  funding_rate: number | null
  account_long_short_ratio: number | null
  oi_change_pct_24h: number | null
}> {
  const parsed = parsePublicSymbol(symbol)
  const [funding, ratio, oi] = await Promise.all([
    analytics(parsed.futuresSymbol, 'funding', 4),
    analytics(parsed.futuresSymbol, 'long-short-ratio', 4),
    analytics(parsed.futuresSymbol, 'open-interest', 25),
  ])
  const relativeRate = (
    funding.data as { relativeRate?: unknown[] } | undefined
  )?.relativeRate
  const ratios = Array.isArray(ratio.data) ? ratio.data : []
  const oiRows = Array.isArray(oi.data) ? oi.data : []
  const lastOi = closeValue(oiRows.at(-1))
  const firstOi = closeValue(oiRows.at(0))
  return {
    symbol: parsed.publicSymbol,
    funding_rate:
      relativeRate && relativeRate.length > 0
        ? closeValue(relativeRate.at(-1))
        : null,
    account_long_short_ratio:
      ratios.length > 0 ? numeric(ratios.at(-1)) : null,
    oi_change_pct_24h:
      firstOi > 0 && lastOi > 0 ? ((lastOi - firstOi) / firstOi) * 100 : null,
  }
}

export async function fetchCryptoAiContext(symbol: string): Promise<Readonly<{
  symbol: string
  mark_price: number
  index_price: number
  basis_pct: number
  open_interest_usd: number
  funding_rate: number | null
  account_long_short_ratio: number | null
  oi_change_pct_24h: number | null
  as_of: string
}>> {
  const parsed = parsePublicSymbol(symbol)
  const [metrics, tickers] = await Promise.all([
    metricsItem(parsed.publicSymbol),
    futuresTickers(),
  ])
  const ticker = tickers.find((item) => item.symbol === parsed.futuresSymbol)
  if (!ticker) throw new HttpError(404, '未找到该 Kraken 永续合约')
  const mark = finite(ticker.markPrice)
  const index = finite(ticker.indexPrice)
  return {
    symbol: parsed.publicSymbol,
    mark_price: mark,
    index_price: index,
    basis_pct: index > 0 ? ((mark - index) / index) * 100 : 0,
    open_interest_usd: finite(ticker.openInterest) * mark,
    funding_rate: metrics.funding_rate,
    account_long_short_ratio: metrics.account_long_short_ratio,
    oi_change_pct_24h: metrics.oi_change_pct_24h,
    as_of: ticker.lastTime ?? new Date().toISOString(),
  }
}

async function getTickers(
  request: Request,
  requestId: string,
): Promise<Response> {
  const url = new URL(request.url)
  const instrument = url.searchParams.get('instrument') ?? 'perp'
  const sortBy = url.searchParams.get('sort_by') ?? 'change_pct_24h'
  const order = url.searchParams.get('order') ?? 'desc'
  const top = Number(url.searchParams.get('top') ?? '100')
  if (instrument !== 'spot' && instrument !== 'perp') {
    throw new HttpError(400, 'instrument 仅支持 spot 或 perp')
  }
  if (!Number.isSafeInteger(top) || top < 1 || top > 1_000) {
    throw new HttpError(400, 'top 必须在 1 到 1000 之间')
  }
  const items =
    instrument === 'perp' ? await perpTickerItems() : await spotTickerItems()
  return cachedJson(
    {
      instrument,
      sort_by: sortBy,
      order,
      items: sortedItems(items, sortBy, order, top),
      source: 'Kraken public market data',
    },
    requestId,
    request.method,
  )
}

async function getOverview(
  request: Request,
  requestId: string,
): Promise<Response> {
  const [tickerResult, globalResult, fearGreedResult] =
    await Promise.allSettled([
      futuresTickers(),
      fetchCryptoGlobal(),
      fetchFearGreed(),
    ] as const)
  const rawTickers = tickerResult.status === 'fulfilled'
    ? tickerResult.value
    : []
  const items = rawTickers.flatMap((ticker) => {
    const item = toPerpTicker(ticker)
    return item ? [item] : []
  })
  const byChange = [...items].sort(
    (left, right) => right.change_pct_24h - left.change_pct_24h,
  )
  const byVolume = [...items].sort(
    (left, right) => right.quote_volume_24h - left.quote_volume_24h,
  )
  const now = new Date().toISOString()
  const derivativesOiUsd = rawTickers.reduce(
    (sum, ticker) =>
      ticker.symbol?.startsWith('PF_')
        ? sum + finite(ticker.openInterest) * finite(ticker.markPrice)
        : sum,
    0,
  )
  const global = globalResult.status === 'fulfilled'
    ? globalResult.value
    : {
        total_market_cap_usd: 0,
        total_volume_24h_usd: 0,
        btc_dominance: 0,
        eth_dominance: 0,
        source: null,
      }
  const fearGreed = fearGreedResult.status === 'fulfilled'
    ? fearGreedResult.value
    : { value: 0, classification: 'N/A' }
  const unavailableFields = [
    ...(globalResult.status === 'rejected'
      ? [
          'total_market_cap_usd',
          'total_volume_24h_usd',
          'btc_dominance',
          'eth_dominance',
        ]
      : []),
    ...(fearGreedResult.status === 'rejected'
      ? ['fear_greed_value']
      : []),
    ...(tickerResult.status === 'rejected'
      ? ['derivatives_oi_usd', 'derivatives_volume_24h_usd']
      : []),
  ]
  return cachedJson(
    {
      market_overview: {
        ts: now,
        total_market_cap_usd: global.total_market_cap_usd,
        total_volume_24h_usd: global.total_volume_24h_usd,
        btc_dominance: global.btc_dominance,
        eth_dominance: global.eth_dominance,
        fear_greed_value: fearGreed.value,
        fear_greed_classification: fearGreed.classification,
        derivatives_oi_usd: derivativesOiUsd,
        derivatives_volume_24h_usd: items.reduce(
          (sum, item) => sum + item.quote_volume_24h,
          0,
        ),
      },
      top_gainers: byChange.slice(0, 10),
      top_losers: byChange.slice(-10).reverse(),
      top_volume: byVolume.slice(0, 10),
      btc_ticker: items.find((item) => item.symbol === 'BTC/USDT') ?? null,
      eth_ticker: items.find((item) => item.symbol === 'ETH/USDT') ?? null,
      source: `${global.source ?? 'Global source unavailable'} + Alternative.me + Kraken Futures`,
      sources: [
        {
          name: 'coingecko',
          ok: global.source === 'coingecko',
        },
        {
          name: 'coinpaprika',
          ok: global.source === 'coinpaprika',
        },
        {
          name: 'coinlore',
          ok: global.source === 'coinlore',
        },
        {
          name: 'alternative_me',
          ok: fearGreedResult.status === 'fulfilled',
        },
        {
          name: 'kraken_futures',
          ok: tickerResult.status === 'fulfilled',
        },
      ],
      unavailable_fields: unavailableFields,
    },
    requestId,
    request.method,
  )
}

async function getMetrics(
  request: Request,
  requestId: string,
): Promise<Response> {
  const url = new URL(request.url)
  const symbols = [...new Set(
    (url.searchParams.get('symbols') ?? '')
      .split(',')
      .map((symbol) => symbol.trim().toUpperCase())
      .filter(Boolean),
  )]
  if (symbols.length === 0) throw new HttpError(400, 'symbols 不能为空')
  const selected = symbols.slice(0, MAX_METRICS_SYMBOLS)
  const settled = await Promise.allSettled(selected.map(metricsItem))
  const items = settled.flatMap((result) =>
    result.status === 'fulfilled' ? [result.value] : [],
  )
  return cachedJson(
    {
      items,
      requested: symbols.length,
      processed: selected.length,
      truncated: symbols.length > selected.length,
      source: 'Kraken futures analytics',
    },
    requestId,
    request.method,
  )
}

async function getFuturesInfo(
  request: Request,
  requestId: string,
  symbol: string,
): Promise<Response> {
  const parsed = parsePublicSymbol(symbol)
  const ticker = (await futuresTickers()).find(
    (item) => item.symbol === parsed.futuresSymbol,
  )
  if (!ticker) throw new HttpError(404, '未找到该 Kraken 永续合约')
  const mark = finite(ticker.markPrice)
  const index = finite(ticker.indexPrice)
  const fundingRate =
    index > 0 ? finite(ticker.fundingRate) / index : 0
  const nextHour = new Date()
  nextHour.setUTCMinutes(0, 0, 0)
  nextHour.setUTCHours(nextHour.getUTCHours() + 1)
  return cachedJson(
    {
      symbol: parsed.publicSymbol,
      base_asset: parsed.base,
      quote_asset: 'USDT',
      contract_type: 'perpetual',
      mark_price: mark,
      index_price: index,
      last_funding_rate: fundingRate,
      next_funding_time: nextHour.toISOString(),
      max_leverage: 0,
      open_interest_coin: finite(ticker.openInterest),
      open_interest_usd: finite(ticker.openInterest) * mark,
      source: 'Kraken perpetual futures',
    },
    requestId,
    request.method,
  )
}

async function getOpenInterest(
  request: Request,
  requestId: string,
  symbol: string,
): Promise<Response> {
  const parsed = parsePublicSymbol(symbol)
  const url = new URL(request.url)
  const limit = boundedLimit(url, 96, 500)
  try {
    const binanceUrl = new URL(
      `${BINANCE_FUTURES_URL}/futures/data/openInterestHist`,
    )
    binanceUrl.searchParams.set('symbol', parsed.publicSymbol)
    binanceUrl.searchParams.set('period', '5m')
    binanceUrl.searchParams.set('limit', String(Math.min(limit, 500)))
    const rows = await fetchPublicJson<Array<{
      timestamp?: unknown
      sumOpenInterest?: unknown
      sumOpenInterestValue?: unknown
    }>>(binanceUrl, 'Binance Futures')
    if (!Array.isArray(rows) || rows.length === 0) {
      throw new Error('Binance Futures returned no OI rows')
    }
    return cachedJson(
      {
        symbol: parsed.publicSymbol,
        items: rows.map((row) => ({
          symbol: parsed.publicSymbol,
          ts: new Date(numeric(row.timestamp)).toISOString(),
          oi_coin: numeric(row.sumOpenInterest),
          oi_usd: numeric(row.sumOpenInterestValue),
        })),
        source: 'Binance Futures open interest',
      },
      requestId,
      request.method,
    )
  } catch {
    try {
      const okxUrl = new URL(
        `${OKX_PUBLIC_URL}/rubik/stat/contracts/open-interest-history`,
      )
      okxUrl.searchParams.set('instId', `${parsed.base}-USDT-SWAP`)
      okxUrl.searchParams.set('period', '5m')
      okxUrl.searchParams.set('limit', String(Math.min(limit, 100)))
      const payload = await fetchPublicJson<{
        code?: string
        data?: unknown[][]
      }>(okxUrl, 'OKX')
      const rows = payload.code === '0' && Array.isArray(payload.data)
        ? payload.data
        : []
      if (rows.length === 0) throw new Error('OKX returned no OI rows')
      return cachedJson(
        {
          symbol: parsed.publicSymbol,
          items: rows.slice(0, limit).reverse().map((row) => ({
            symbol: parsed.publicSymbol,
            ts: new Date(numeric(row[0])).toISOString(),
            oi_coin: numeric(row[2] ?? row[1]),
            oi_usd: numeric(row[3]),
          })),
          source: 'OKX open interest history',
        },
        requestId,
        request.method,
      )
    } catch {
      // Kraken remains the final no-key source for symbols unavailable on
      // Binance and OKX.
    }
  }
  const [series, tickers] = await Promise.all([
    analytics(parsed.futuresSymbol, 'open-interest', Math.max(limit, 24)),
    futuresTickers(),
  ])
  const timestamps = timestampsToIso(series.timestamp)
  const rows = Array.isArray(series.data) ? series.data : []
  const mark = finite(
    tickers.find((ticker) => ticker.symbol === parsed.futuresSymbol)?.markPrice,
  )
  const items = rows.slice(-limit).map((row, index) => {
    const oiCoin = closeValue(row)
    const timestamp = timestamps.at(timestamps.length - rows.slice(-limit).length + index)
    return {
      symbol: parsed.publicSymbol,
      ts: timestamp ?? new Date().toISOString(),
      oi_coin: oiCoin,
      oi_usd: oiCoin * mark,
    }
  })
  return cachedJson(
    { symbol: parsed.publicSymbol, items, source: 'Kraken futures analytics' },
    requestId,
    request.method,
  )
}

async function getLongShortRatio(
  request: Request,
  requestId: string,
  symbol: string,
): Promise<Response> {
  const parsed = parsePublicSymbol(symbol)
  const limit = boundedLimit(new URL(request.url), 96, 500)
  try {
    const endpoint = async <T>(path: string): Promise<T> => {
      const url = new URL(`${BINANCE_FUTURES_URL}/futures/data/${path}`)
      url.searchParams.set('symbol', parsed.publicSymbol)
      url.searchParams.set('period', '5m')
      url.searchParams.set('limit', String(Math.min(limit, 500)))
      return fetchPublicJson<T>(url, 'Binance Futures')
    }
    type RatioRow = {
      timestamp?: unknown
      longAccount?: unknown
      shortAccount?: unknown
      longShortRatio?: unknown
    }
    type TakerRow = {
      timestamp?: unknown
      buyVol?: unknown
      sellVol?: unknown
      buySellRatio?: unknown
    }
    const [accounts, positions, globalAccounts, takers] = await Promise.all([
      endpoint<RatioRow[]>('topLongShortAccountRatio'),
      endpoint<RatioRow[]>('topLongShortPositionRatio'),
      endpoint<RatioRow[]>('globalLongShortAccountRatio'),
      endpoint<TakerRow[]>('takerlongshortRatio'),
    ])
    if (
      !Array.isArray(accounts) ||
      !Array.isArray(positions) ||
      !Array.isArray(globalAccounts) ||
      !Array.isArray(takers) ||
      accounts.length === 0
    ) {
      throw new Error('Binance Futures returned incomplete ratio rows')
    }
    const byTimestamp = <T extends { timestamp?: unknown }>(rows: T[]) =>
      new Map(rows.map((row) => [numeric(row.timestamp), row]))
    const positionByTs = byTimestamp(positions)
    const globalByTs = byTimestamp(globalAccounts)
    const takerByTs = byTimestamp(takers)
    const items = accounts.map((account) => {
      const timestamp = numeric(account.timestamp)
      const position = positionByTs.get(timestamp)
      const globalAccount = globalByTs.get(timestamp)
      const taker = takerByTs.get(timestamp)
      return {
        symbol: parsed.publicSymbol,
        ts: new Date(timestamp).toISOString(),
        top_account_long: numeric(account.longAccount),
        top_account_short: numeric(account.shortAccount),
        top_account_ratio: numeric(account.longShortRatio),
        top_position_long: numeric(position?.longAccount),
        top_position_short: numeric(position?.shortAccount),
        top_position_ratio: numeric(position?.longShortRatio),
        taker_buy_vol: numeric(taker?.buyVol),
        taker_sell_vol: numeric(taker?.sellVol),
        taker_ratio: numeric(taker?.buySellRatio),
        global_account_long: numeric(globalAccount?.longAccount),
        global_account_short: numeric(globalAccount?.shortAccount),
        global_account_ratio: numeric(globalAccount?.longShortRatio),
      }
    })
    return cachedJson(
      {
        symbol: parsed.publicSymbol,
        items,
        source: 'Binance Futures positioning and taker flow',
        unavailable_fields: [],
      },
      requestId,
      request.method,
    )
  } catch {
    try {
      const ratioUrl = new URL(
        `${OKX_PUBLIC_URL}/rubik/stat/contracts/long-short-account-ratio`,
      )
      ratioUrl.searchParams.set('ccy', parsed.base)
      ratioUrl.searchParams.set('period', '5m')
      const takerUrl = new URL(
        `${OKX_PUBLIC_URL}/rubik/stat/taker-volume-contract`,
      )
      takerUrl.searchParams.set('instId', `${parsed.base}-USDT-SWAP`)
      takerUrl.searchParams.set('period', '5m')
      type OkxRows = { code?: string; data?: unknown[][] }
      const [ratioPayload, takerPayload] = await Promise.all([
        fetchPublicJson<OkxRows>(ratioUrl, 'OKX'),
        fetchPublicJson<OkxRows>(takerUrl, 'OKX'),
      ])
      const ratios = ratioPayload.code === '0' && Array.isArray(ratioPayload.data)
        ? ratioPayload.data
        : []
      const takers = takerPayload.code === '0' && Array.isArray(takerPayload.data)
        ? takerPayload.data
        : []
      if (ratios.length === 0) throw new Error('OKX returned no ratio rows')
      const takerByTs = new Map(
        takers.map((row) => [numeric(row[0]), row]),
      )
      const items = ratios.slice(0, limit).reverse().map((row) => {
        const timestamp = numeric(row[0])
        const ratio = numeric(row[1])
        const taker = takerByTs.get(timestamp)
        const globalLong = ratio > 0 ? ratio / (1 + ratio) : 0
        const globalShort = ratio > 0 ? 1 / (1 + ratio) : 0
        const sellVolume = numeric(taker?.[1])
        const buyVolume = numeric(taker?.[2])
        return {
          symbol: parsed.publicSymbol,
          ts: new Date(timestamp).toISOString(),
          top_account_long: 0,
          top_account_short: 0,
          top_account_ratio: 0,
          top_position_long: 0,
          top_position_short: 0,
          top_position_ratio: 0,
          taker_buy_vol: buyVolume,
          taker_sell_vol: sellVolume,
          taker_ratio: sellVolume > 0 ? buyVolume / sellVolume : 0,
          global_account_long: globalLong,
          global_account_short: globalShort,
          global_account_ratio: ratio,
        }
      })
      return cachedJson(
        {
          symbol: parsed.publicSymbol,
          items,
          source: 'OKX global positioning and taker flow',
          unavailable_fields: ['top_account_ratio', 'top_position_ratio'],
        },
        requestId,
        request.method,
      )
    } catch {
      // Preserve Kraken analytics as the final no-key fallback.
    }
  }
  const series = await analytics(
    parsed.futuresSymbol,
    'long-short-ratio',
    Math.max(limit, 24),
  )
  const timestamps = timestampsToIso(series.timestamp)
  const rows = Array.isArray(series.data) ? series.data : []
  const start = Math.max(0, rows.length - limit)
  const items = rows.slice(-limit).map((row, index) => {
    const ratio = numeric(row)
    const long = ratio > 0 ? ratio / (1 + ratio) : 0
    const short = ratio > 0 ? 1 / (1 + ratio) : 0
    return {
      symbol: parsed.publicSymbol,
      ts: timestamps[start + index] ?? new Date().toISOString(),
      top_account_long: long,
      top_account_short: short,
      top_account_ratio: ratio,
      top_position_long: 0,
      top_position_short: 0,
      top_position_ratio: 0,
      taker_buy_vol: 0,
      taker_sell_vol: 0,
      taker_ratio: 0,
      global_account_long: 0,
      global_account_short: 0,
      global_account_ratio: 0,
    }
  })
  return cachedJson(
    {
      symbol: parsed.publicSymbol,
      items,
      source: 'Kraken futures long-short ratio',
      unavailable_fields: ['top_position_ratio', 'taker_ratio', 'global_account_ratio'],
    },
    requestId,
    request.method,
  )
}

async function getFundingRate(
  request: Request,
  requestId: string,
  symbol: string,
): Promise<Response> {
  const parsed = parsePublicSymbol(symbol)
  const limit = boundedLimit(new URL(request.url), 100, 500)
  const [series, tickers] = await Promise.all([
    analytics(parsed.futuresSymbol, 'funding', Math.max(limit, 24)),
    futuresTickers(),
  ])
  const timestamps = timestampsToIso(series.timestamp)
  const rates = (
    series.data as { relativeRate?: unknown[] } | undefined
  )?.relativeRate ?? []
  const start = Math.max(0, rates.length - limit)
  const mark = finite(
    tickers.find((ticker) => ticker.symbol === parsed.futuresSymbol)?.markPrice,
  )
  const items = rates.slice(-limit).map((row, index) => ({
    symbol: parsed.publicSymbol,
    ts: timestamps[start + index] ?? new Date().toISOString(),
    rate: closeValue(row),
    mark_price: mark,
  }))
  return cachedJson(
    { symbol: parsed.publicSymbol, items, source: 'Kraken futures funding analytics' },
    requestId,
    request.method,
  )
}

async function getBasis(
  request: Request,
  requestId: string,
  symbol: string,
): Promise<Response> {
  const parsed = parsePublicSymbol(symbol)
  const ticker = (await futuresTickers()).find(
    (item) => item.symbol === parsed.futuresSymbol,
  )
  if (!ticker) throw new HttpError(404, '未找到该 Kraken 永续合约')
  const mark = finite(ticker.markPrice)
  const index = finite(ticker.indexPrice)
  const items = index > 0
    ? [{
        ts: ticker.lastTime ?? new Date().toISOString(),
        mark_price: mark,
        index_price: index,
        basis_pct: ((mark - index) / index) * 100,
      }]
    : []
  return cachedJson(
    { symbol: parsed.publicSymbol, items, source: 'Kraken current mark/index price' },
    requestId,
    request.method,
  )
}

function boundedLimit(url: URL, fallback: number, max: number): number {
  const limit = Number(url.searchParams.get('limit') ?? String(fallback))
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > max) {
    throw new HttpError(400, `limit 必须在 1 到 ${max} 之间`)
  }
  return limit
}

export async function handleCryptoMarketRoute(
  request: Request,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (!path.startsWith('/api/v1/crypto/')) return null
  if (request.method !== 'GET') {
    return jsonResponse({ detail: 'Method not allowed' }, 405, requestId, request.method)
  }
  if (path === '/api/v1/crypto/tickers/24h') {
    return getTickers(request, requestId)
  }
  if (path === '/api/v1/crypto/overview') {
    return getOverview(request, requestId)
  }
  if (path === '/api/v1/crypto/futures/metrics-batch') {
    return getMetrics(request, requestId)
  }
  if (path === '/api/v1/crypto/boll-scan') {
    return cachedJson(
      {
        as_of: null,
        count: 0,
        disclaimer: '',
        items: [],
      },
      requestId,
      request.method,
    )
  }
  const bollMatch = path.match(/^\/api\/v1\/crypto\/boll-structure\/([^/]+)$/u)
  if (bollMatch?.[1]) {
    const parsed = parsePublicSymbol(decodeURIComponent(bollMatch[1]))
    return cachedJson(
      {
        symbol: parsed.publicSymbol,
        available: false,
        source: 'none',
        layer: '布林结构',
        as_of: null,
        item: null,
        disclaimer: '',
      },
      requestId,
      request.method,
    )
  }
  const futuresMatch = path.match(
    /^\/api\/v1\/crypto\/futures\/([^/]+)\/(open-interest|long-short-ratio|funding-rate|info|basis)$/u,
  )
  if (futuresMatch?.[1] && futuresMatch[2]) {
    const symbol = decodeURIComponent(futuresMatch[1])
    switch (futuresMatch[2]) {
      case 'open-interest':
        return getOpenInterest(request, requestId, symbol)
      case 'long-short-ratio':
        return getLongShortRatio(request, requestId, symbol)
      case 'funding-rate':
        return getFundingRate(request, requestId, symbol)
      case 'info':
        return getFuturesInfo(request, requestId, symbol)
      case 'basis':
        return getBasis(request, requestId, symbol)
    }
  }
  return jsonResponse({ detail: 'Route not found' }, 404, requestId, request.method)
}
