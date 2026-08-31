import { HttpError, jsonResponse } from './http'

const MARKETS = new Set(['cn', 'us', 'hk', 'crypto'])
const PERIODS = new Set(['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'])

export type Kline = Readonly<{
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number | null
}>

export type KlineFetchResult = Readonly<{
  items: Kline[]
  source: string
  fallback_used: boolean
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
    case '4h':
      // Yahoo does not expose a native four-hour bar. Fetch hourly bars and
      // aggregate them below so every market shares the same public periods.
      return { interval: '1h', range: '3mo' }
    case '1d':
      return { interval: '1d', range: '2y' }
    case '1w':
      return { interval: '1wk', range: '10y' }
    default:
      throw new HttpError(400, '周期不受支持')
  }
}

function aggregateBars(
  items: Kline[],
  size: number,
  timeZone: string,
): Kline[] {
  if (size <= 1) return items
  const result: Kline[] = []
  const dateFormatter = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  const sessions = new Map<string, Kline[]>()
  for (const item of items) {
    const date = dateFormatter.format(new Date(item.ts))
    const session = sessions.get(date)
    if (session) session.push(item)
    else sessions.set(date, [item])
  }
  for (const session of sessions.values()) {
    for (let index = 0; index < session.length; index += size) {
      const window = session.slice(index, index + size)
      const first = window[0]
      const last = window.at(-1)
      if (!first || !last) continue
      const amounts = window.map((item) => item.amount)
      result.push({
        ts: first.ts,
        open: first.open,
        high: Math.max(...window.map((item) => item.high)),
        low: Math.min(...window.map((item) => item.low)),
        close: last.close,
        volume: window.reduce((total, item) => total + item.volume, 0),
        amount: amounts.every((amount) => amount !== null)
          ? amounts.reduce((total, amount) => total + (amount ?? 0), 0)
          : null,
      })
    }
  }
  return result
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

async function fetchYahooKlinesFromHost(
  symbol: string,
  market: string,
  period: string,
  limit: number,
  host: 'query1.finance.yahoo.com' | 'query2.finance.yahoo.com',
): Promise<Kline[]> {
  const upstreamSymbol = yahooSymbol(symbol, market)
  const { interval, range } = yahooPeriod(period)
  const url = new URL(
    `https://${host}/v8/finance/chart/${encodeURIComponent(upstreamSymbol)}`,
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
  if (items.length === 0) throw new HttpError(404, '标的暂无有效行情')
  return (period === '4h'
    ? aggregateBars(
        items,
        4,
        market === 'us' ? 'America/New_York' : 'Asia/Shanghai',
      )
    : items).slice(-limit)
}

async function fetchEastmoneyKlines(
  symbol: string,
  market: 'cn' | 'hk',
  period: string,
  limit: number,
): Promise<Kline[]> {
  const normalized = symbol.trim().toUpperCase()
  const secid = market === 'hk'
    ? `116.${normalized.padStart(5, '0')}`
    : `${normalized.startsWith('6') ? '1' : '0'}.${normalized}`
  const klt = eastmoneyPeriods[period as keyof typeof eastmoneyPeriods]
  if (!klt) throw new HttpError(400, '周期不受支持')
  const url = new URL('https://push2his.eastmoney.com/api/qt/stock/kline/get')
  url.searchParams.set('secid', secid)
  url.searchParams.set('klt', klt)
  url.searchParams.set('fqt', '1')
  url.searchParams.set('lmt', String(Math.min(period === '4h' ? limit * 4 : limit, 5_000)))
  url.searchParams.set('end', '20500101')
  url.searchParams.set('fields1', 'f1,f2,f3,f4,f5,f6')
  url.searchParams.set('fields2', 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
  const response = await fetch(url, {
    headers: {
      referer: 'https://quote.eastmoney.com/',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) throw new HttpError(503, `东方财富行情暂不可用（HTTP ${response.status}）`)
  const payload = (await response.json()) as {
    data?: { klines?: string[] } | null
  }
  const closeTime = market === 'hk' ? '16:00:00' : '15:00:00'
  const items = (payload.data?.klines ?? []).flatMap((line) => {
    const row = line.split(',')
    const date = row[0]
    const open = Number(row[1])
    const close = Number(row[2])
    const high = Number(row[3])
    const low = Number(row[4])
    const volume = Number(row[5])
    const amount = Number(row[6])
    if (!date || !validOhlc(open, high, low, close)) return []
    const localDate = date.replace(' ', 'T') +
      (date.includes(' ') && date.length === 16 ? ':00' : '')
    const timestamp = new Date(
      `${date.includes(' ') ? localDate : `${date}T${closeTime}`}+08:00`,
    )
    if (!Number.isFinite(timestamp.getTime())) return []
    return [{
      ts: timestamp.toISOString(),
      open,
      high,
      low,
      close,
      volume: Number.isFinite(volume) && volume >= 0 ? volume : 0,
      amount: Number.isFinite(amount) && amount >= 0 ? amount : null,
    }]
  })
  if (items.length === 0) throw new HttpError(404, '标的暂无有效行情')
  return (period === '4h'
    ? aggregateBars(items, 4, 'Asia/Shanghai')
    : items).slice(-limit)
}

const eastmoneyPeriods = {
  '1m': '1',
  '5m': '5',
  '15m': '15',
  '30m': '30',
  '1h': '60',
  '4h': '60',
  '1d': '101',
  '1w': '102',
} as const

async function fetchYahooKlines(
  symbol: string,
  market: string,
  period: string,
  limit: number,
): Promise<KlineFetchResult> {
  try {
    return {
      items: await fetchYahooKlinesFromHost(
        symbol,
        market,
        period,
        limit,
        'query1.finance.yahoo.com',
      ),
      source: 'Yahoo Finance query1',
      fallback_used: false,
    }
  } catch (primaryError) {
    if (market === 'cn' || market === 'hk') {
      try {
        return {
          items: await fetchEastmoneyKlines(symbol, market, period, limit),
          source: 'Eastmoney public market data',
          fallback_used: true,
        }
      } catch {
        // Continue to Yahoo query2 so one backup failure does not hide another.
      }
    }
    try {
      return {
        items: await fetchYahooKlinesFromHost(
          symbol,
          market,
          period,
          limit,
          'query2.finance.yahoo.com',
        ),
        source: 'Yahoo Finance query2',
        fallback_used: true,
      }
    } catch (fallbackError) {
      if (
        primaryError instanceof HttpError &&
        fallbackError instanceof HttpError &&
        primaryError.status === 404 &&
        fallbackError.status === 404
      ) {
        throw new HttpError(404, '标的不存在')
      }
      throw new HttpError(503, '股票行情主备入口均暂不可用')
    }
  }
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
    '4h': 240,
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

function cryptoBase(symbol: string): string {
  const normalized = symbol.trim().toUpperCase()
  const quoted = normalized.match(/^([A-Z0-9]{1,20})\/?(?:USDT|USD)$/u)
  if (quoted?.[1]) return quoted[1]
  if (!/^[A-Z0-9]{1,20}$/u.test(normalized)) {
    throw new HttpError(400, '数字资产标的格式无效')
  }
  return normalized
}

function bybitInterval(period: string): string {
  const intervals: Readonly<Record<string, string>> = {
    '1m': '1',
    '5m': '5',
    '15m': '15',
    '30m': '30',
    '1h': '60',
    '4h': '240',
    '1d': 'D',
    '1w': 'W',
  }
  const interval = intervals[period]
  if (!interval) throw new HttpError(400, '周期不受支持')
  return interval
}

async function fetchBybitKlines(
  symbol: string,
  period: string,
  limit: number,
): Promise<Kline[]> {
  const url = new URL('https://api.bybit.com/v5/market/kline')
  url.searchParams.set('category', 'linear')
  url.searchParams.set('symbol', `${cryptoBase(symbol)}USDT`)
  url.searchParams.set('interval', bybitInterval(period))
  url.searchParams.set('limit', String(Math.min(limit, 1_000)))
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) {
    throw new HttpError(503, `Bybit 合约 K 线暂不可用（HTTP ${response.status}）`)
  }
  const payload = (await response.json()) as {
    retCode?: number
    retMsg?: string
    result?: { list?: unknown[][] }
  }
  if (payload.retCode !== 0) {
    throw new HttpError(503, payload.retMsg || 'Bybit 合约 K 线返回异常')
  }
  return (payload.result?.list ?? []).flatMap((row) => {
    const timestamp = Number(row[0])
    const open = Number(row[1])
    const high = Number(row[2])
    const low = Number(row[3])
    const close = Number(row[4])
    const volume = Number(row[5])
    const amount = Number(row[6])
    if (!Number.isFinite(timestamp) || !validOhlc(open, high, low, close)) {
      return []
    }
    return [{
      ts: new Date(timestamp).toISOString(),
      open,
      high,
      low,
      close,
      volume: Number.isFinite(volume) && volume >= 0 ? volume : 0,
      amount: Number.isFinite(amount) && amount >= 0 ? amount : null,
    }]
  }).sort((left, right) => left.ts.localeCompare(right.ts)).slice(-limit)
}

function okxBar(period: string): string {
  const bars: Readonly<Record<string, string>> = {
    '1m': '1m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1H',
    '4h': '4H',
    '1d': '1Dutc',
    '1w': '1Wutc',
  }
  const bar = bars[period]
  if (!bar) throw new HttpError(400, '周期不受支持')
  return bar
}

async function fetchOkxKlines(
  symbol: string,
  period: string,
  instrument: 'spot' | 'perp',
  limit: number,
): Promise<Kline[]> {
  const base = cryptoBase(symbol)
  const instId = instrument === 'perp'
    ? `${base}-USDT-SWAP`
    : `${base}-USDT`
  const url = new URL('https://www.okx.com/api/v5/market/candles')
  url.searchParams.set('instId', instId)
  url.searchParams.set('bar', okxBar(period))
  url.searchParams.set('limit', String(Math.min(limit, 300)))
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) {
    throw new HttpError(503, `OKX 行情暂不可用（HTTP ${response.status}）`)
  }
  const payload = (await response.json()) as {
    code?: string
    msg?: string
    data?: unknown[][]
  }
  if (payload.code !== '0') {
    const notFound = payload.code === '51001' || payload.code === '51000'
    throw new HttpError(notFound ? 404 : 503, payload.msg || 'OKX 行情返回异常')
  }
  const items = (payload.data ?? []).flatMap((row) => {
    const timestamp = Number(row[0])
    const open = Number(row[1])
    const high = Number(row[2])
    const low = Number(row[3])
    const close = Number(row[4])
    const volume = Number(row[6] ?? row[5])
    const amount = Number(row[7])
    if (!Number.isFinite(timestamp) || !validOhlc(open, high, low, close)) {
      return []
    }
    return [{
      ts: new Date(timestamp).toISOString(),
      open,
      high,
      low,
      close,
      volume: Number.isFinite(volume) && volume >= 0 ? volume : 0,
      amount: Number.isFinite(amount) && amount >= 0 ? amount : null,
    }]
  })
  return items.sort((left, right) => left.ts.localeCompare(right.ts)).slice(-limit)
}

function krakenFuturesResolution(period: string): string {
  if (!PERIODS.has(period)) throw new HttpError(400, '周期不受支持')
  return period
}

async function fetchKrakenFuturesKlines(
  symbol: string,
  period: string,
  limit: number,
): Promise<Kline[]> {
  const base = cryptoBase(symbol)
  const krakenBase = base === 'BTC' ? 'XBT' : base === 'DOGE' ? 'XDG' : base
  const url = new URL(
    `https://futures.kraken.com/api/charts/v1/trade/PF_${krakenBase}USD/${krakenFuturesResolution(period)}`,
  )
  url.searchParams.set('count', String(Math.min(limit, 5_000)))
  const response = await fetch(url, {
    headers: { accept: 'application/json' },
    signal: AbortSignal.timeout(10_000),
  })
  if (response.status === 404) throw new HttpError(404, 'Kraken 合约不存在')
  if (!response.ok) {
    throw new HttpError(503, `Kraken 合约 K 线暂不可用（HTTP ${response.status}）`)
  }
  const payload = (await response.json()) as {
    candles?: Array<Record<string, unknown>>
  }
  return (payload.candles ?? []).flatMap((row) => {
    const timestamp = Number(row.time)
    const open = Number(row.open)
    const high = Number(row.high)
    const low = Number(row.low)
    const close = Number(row.close)
    const volume = Number(row.volume)
    if (!Number.isFinite(timestamp) || !validOhlc(open, high, low, close)) {
      return []
    }
    return [{
      ts: new Date(timestamp).toISOString(),
      open,
      high,
      low,
      close,
      volume: Number.isFinite(volume) && volume >= 0 ? volume : 0,
      amount: null,
    }]
  }).slice(-limit)
}

async function fetchCryptoKlines(
  symbol: string,
  period: string,
  instrument: 'spot' | 'perp',
  limit: number,
): Promise<KlineFetchResult> {
  const providers: ReadonlyArray<Readonly<{
    source: string
    fetcher: () => Promise<Kline[]>
  }>> = instrument === 'perp'
    ? [
        {
          source: 'Bybit public linear candles',
          fetcher: () => fetchBybitKlines(symbol, period, limit),
        },
        {
          source: 'OKX public perpetual candles',
          fetcher: () => fetchOkxKlines(symbol, period, instrument, limit),
        },
        {
          source: 'Kraken Futures public candles',
          fetcher: () => fetchKrakenFuturesKlines(symbol, period, limit),
        },
      ]
    : [
        {
          source: 'OKX public spot candles',
          fetcher: () => fetchOkxKlines(symbol, period, instrument, limit),
        },
        {
          source: 'Kraken public spot candles',
          fetcher: () => fetchKrakenKlines(symbol, period, limit),
        },
      ]
  const failures: unknown[] = []
  for (const [index, provider] of providers.entries()) {
    try {
      const items = await provider.fetcher()
      if (items.length > 0) {
        return {
          items,
          source: provider.source,
          fallback_used: index > 0,
        }
      }
      failures.push(new HttpError(404, `${provider.source} 未返回数据`))
    } catch (error) {
      failures.push(error)
    }
  }
  const allNotFound = failures.every(
    (error) => error instanceof HttpError && error.status === 404,
  )
  throw new HttpError(
    allNotFound ? 404 : 503,
    allNotFound ? '未找到该数字资产交易对' : '数字资产行情主备源均暂不可用',
  )
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
  const result = await fetchMarketKlines({
    symbol,
    market,
    period,
    instrument: instrument as 'spot' | 'perp',
    limit,
  })
  if (result.items.length === 0) throw new HttpError(404, '未找到 K 线数据')
  const response = jsonResponse(
    {
      symbol,
      market,
      period,
      instrument,
      items: result.items,
      source: result.source,
      fallback_used: result.fallback_used,
      data_as_of: result.items.at(-1)?.ts ?? null,
    },
    200,
    requestId,
    request.method,
  )
  response.headers.set('cache-control', 'public, max-age=15, s-maxage=60')
  return response
}

export async function fetchMarketKlines(input: Readonly<{
  symbol: string
  market: string
  period: string
  instrument: 'spot' | 'perp'
  limit: number
}>): Promise<KlineFetchResult> {
  if (
    !input.symbol ||
    !MARKETS.has(input.market) ||
    !PERIODS.has(input.period)
  ) {
    throw new HttpError(400, 'symbol、market 或 period 格式无效')
  }
  if (
    !Number.isSafeInteger(input.limit) ||
    input.limit < 1 ||
    input.limit > 5_000
  ) {
    throw new HttpError(400, 'limit 必须在 1 到 5000 之间')
  }
  if (input.instrument === 'perp' && input.market !== 'crypto') {
    throw new HttpError(400, 'perp 仅支持数字资产市场')
  }
  return input.market === 'crypto'
    ? fetchCryptoKlines(
        input.symbol,
        input.period,
        input.instrument,
        input.limit,
      )
    : fetchYahooKlines(
        input.symbol,
        input.market,
        input.period,
        input.limit,
      )
}

function normalizedYahooSearchSymbol(
  symbol: string,
  market: string,
): string | null {
  const normalized = symbol.trim().toUpperCase()
  if (market === 'cn') {
    const match = normalized.match(/^(\d{6})\.(?:SS|SZ)$/u)
    return match?.[1] ?? null
  }
  if (market === 'hk') {
    const match = normalized.match(/^(\d{1,5})\.HK$/u)
    return match?.[1]?.padStart(5, '0') ?? null
  }
  if (market === 'us' && /^[A-Z][A-Z0-9.-]{0,14}$/u.test(normalized)) {
    return normalized
  }
  return null
}

async function searchYahooSymbols(
  query: string,
  market: string,
  limit: number,
): Promise<SymbolMeta[]> {
  if (market === 'crypto') return []
  const url = new URL('https://query2.finance.yahoo.com/v1/finance/search')
  url.searchParams.set('q', query)
  url.searchParams.set('quotesCount', String(Math.min(limit * 3, 100)))
  url.searchParams.set('newsCount', '0')
  url.searchParams.set('enableFuzzyQuery', 'true')
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(8_000),
  })
  if (!response.ok) throw new Error(`Yahoo search HTTP ${response.status}`)
  const payload = (await response.json()) as {
    quotes?: Array<{
      symbol?: unknown
      shortname?: unknown
      longname?: unknown
      quoteType?: unknown
    }>
  }
  return (payload.quotes ?? []).flatMap((quote) => {
    const symbol = normalizedYahooSearchSymbol(String(quote.symbol ?? ''), market)
    const quoteType = String(quote.quoteType ?? '').toUpperCase()
    if (!symbol || !['EQUITY', 'ETF', 'INDEX'].includes(quoteType)) return []
    const name = String(quote.longname ?? quote.shortname ?? symbol).trim()
    return [{ symbol, market, name: name || symbol, name_en: name || symbol }]
  }).slice(0, limit)
}

async function searchOkxSymbols(
  query: string,
  limit: number,
): Promise<SymbolMeta[]> {
  const url = new URL('https://www.okx.com/api/v5/public/instruments')
  url.searchParams.set('instType', 'SWAP')
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(8_000),
  })
  if (!response.ok) throw new Error(`OKX instruments HTTP ${response.status}`)
  const payload = (await response.json()) as {
    code?: string
    data?: Array<{ instId?: unknown; baseCcy?: unknown; state?: unknown }>
  }
  if (payload.code !== '0') throw new Error('OKX instruments payload invalid')
  const normalizedQuery = query.toUpperCase().replace(/[^A-Z0-9]/gu, '')
  if (!normalizedQuery) return []
  return (payload.data ?? []).flatMap((instrument) => {
    const instId = String(instrument.instId ?? '').toUpperCase()
    const match = instId.match(/^([A-Z0-9]{2,20})-USDT-SWAP$/u)
    const base = match?.[1]
    if (
      !base ||
      instrument.state !== 'live' ||
      (!base.includes(normalizedQuery) && !instId.includes(normalizedQuery))
    ) {
      return []
    }
    return [{
      symbol: `${base}/USDT`,
      market: 'crypto',
      name: base,
      name_en: base,
    }]
  }).slice(0, limit)
}

async function searchSymbols(
  request: Request,
  requestId: string,
): Promise<Response> {
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
  const localItems = SYMBOLS.filter(
    (item) =>
      (!market || item.market === market) &&
      [item.symbol, item.name, item.name_en ?? ''].some((value) =>
        value.toLowerCase().includes(query),
      ),
  ).slice(0, limit)
  let remoteItems: SymbolMeta[] = []
  try {
    remoteItems = market === 'crypto'
      ? await searchOkxSymbols(query, limit)
      : market
        ? await searchYahooSymbols(query, market, limit)
        : (await Promise.allSettled([
            searchYahooSymbols(query, 'us', limit),
            searchYahooSymbols(query, 'cn', limit),
            searchYahooSymbols(query, 'hk', limit),
            searchOkxSymbols(query, limit),
          ])).flatMap((result) =>
            result.status === 'fulfilled' ? result.value : [],
          )
  } catch (error) {
    console.warn(
      JSON.stringify({
        event: 'market.symbol_search_fallback',
        market,
        error: error instanceof Error ? error.message : String(error),
      }),
    )
  }
  const seen = new Set<string>()
  const items = [...localItems, ...remoteItems]
    .filter((item) => {
      const key = `${item.market}:${item.symbol}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, limit)
    .map((item) => ({
      ...item,
      listed_date: null,
      is_active: true,
      updated_at: updatedAt,
    }))
  const response = jsonResponse(items, 200, requestId, request.method)
  response.headers.set('cache-control', 'public, max-age=60, s-maxage=3600')
  return response
}

async function dataSourceHealth(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const [stockProbes, cryptoProbe, boards, overview] = await Promise.all([
    Promise.all(([
      ['cn', '600519'],
      ['us', 'AAPL'],
      ['hk', '00700'],
    ] as const).map(async ([market, symbol]) => {
      try {
        const result = await fetchYahooKlines(symbol, market, '1d', 1)
        return [market, {
          ok: result.items.length > 0,
          source: result.source,
          data_as_of: result.items.at(-1)?.ts ?? null,
        }] as const
      } catch (error) {
        return [market, {
          ok: false,
          source: market === 'us'
            ? 'Yahoo Finance query1/query2'
            : 'Yahoo Finance/Eastmoney',
          error: error instanceof Error ? error.message : String(error),
        }] as const
      }
    })),
    fetchCryptoKlines('AGLD/USDT', '1h', 'perp', 1)
      .then((result) => ({
        ok: result.items.length > 0,
        source: result.source,
        data_as_of: result.items.at(-1)?.ts ?? null,
      }))
      .catch((error) => ({
        ok: false,
        source: 'OKX/Kraken Futures',
        error: error instanceof Error ? error.message : String(error),
      })),
    env.DB
      .prepare(
        `SELECT market, quoted_at
         FROM market_home_boards
         WHERE market IN ('cn', 'us', 'hk')
         ORDER BY market`,
      )
      .all<{ market: string; quoted_at: number }>(),
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count, MAX(quoted_at) AS quoted_at
         FROM market_overview_quotes`,
      )
      .first<{ count: number; quoted_at: number | null }>(),
  ])
  const boardStatus = Object.fromEntries(
    boards.results.map((row) => [
      row.market,
      {
        ok: true,
        data_as_of: new Date(row.quoted_at).toISOString(),
        storage: 'midas-trading-db',
      },
    ]),
  )
  const stockStatus = Object.fromEntries(stockProbes)
  const components = {
    crypto_kline: cryptoProbe,
    cn_kline: stockStatus.cn,
    us_kline: stockStatus.us,
    hk_kline: stockStatus.hk,
    cn_board: boardStatus.cn ?? { ok: false },
    us_board: boardStatus.us ?? { ok: false },
    hk_board: boardStatus.hk ?? { ok: false },
    global_overview: {
      ok: (overview?.count ?? 0) > 0,
      item_count: overview?.count ?? 0,
      data_as_of: overview?.quoted_at
        ? new Date(overview.quoted_at).toISOString()
        : null,
      storage: 'midas-trading-db',
    },
  }
  const allHealthy = Object.values(components).every(
    (component) => component.ok,
  )
  const response = jsonResponse(
    {
      status: allHealthy ? 'ok' : 'degraded',
      checked_at: new Date().toISOString(),
      components,
    },
    200,
    requestId,
    request.method,
  )
  response.headers.set('cache-control', 'no-store')
  return response
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
  if (
    path === '/api/v1/market/data-sources/health' &&
    request.method === 'GET'
  ) {
    return dataSourceHealth(request, env, requestId)
  }
  if (path === '/api/v1/market/symbols' && request.method === 'GET') {
    return await searchSymbols(request, requestId)
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
