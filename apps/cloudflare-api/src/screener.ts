import { HttpError, jsonResponse, readJsonObject } from './http'

type Market = 'cn' | 'us' | 'hk'

type BoardRow = Readonly<{
  symbol: string
  name: string
  market: Market
  last_price: number
  change_pct: number
  amount: number
}>

type Filters = Readonly<{
  price_min: number | null
  price_max: number | null
  change_pct_min: number | null
  change_pct_max: number | null
  rsi_min: number | null
  rsi_max: number | null
  ma_bull_aligned: boolean
  macd_golden_cross: boolean
  kdj_golden_cross: boolean
  boll_bandwidth_max: number | null
  volume_ratio_min: number | null
}>

type Candle = Readonly<{
  high: number
  low: number
  close: number
  volume: number
}>

function optionalNumber(
  body: Readonly<Record<string, unknown>>,
  key: string,
): number | null {
  const value = body[key]
  if (value === undefined || value === null || value === '') return null
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new HttpError(400, `${key} 必须是有限数值`)
  }
  return value
}

function optionalBoolean(
  body: Readonly<Record<string, unknown>>,
  key: string,
): boolean {
  const value = body[key]
  if (value === undefined || value === null) return false
  if (typeof value !== 'boolean') throw new HttpError(400, `${key} 必须是布尔值`)
  return value
}

function parseFilters(body: Readonly<Record<string, unknown>>): Filters {
  const filters = {
    price_min: optionalNumber(body, 'price_min'),
    price_max: optionalNumber(body, 'price_max'),
    change_pct_min: optionalNumber(body, 'change_pct_min'),
    change_pct_max: optionalNumber(body, 'change_pct_max'),
    rsi_min: optionalNumber(body, 'rsi_min'),
    rsi_max: optionalNumber(body, 'rsi_max'),
    ma_bull_aligned: optionalBoolean(body, 'ma_bull_aligned'),
    macd_golden_cross: optionalBoolean(body, 'macd_golden_cross'),
    kdj_golden_cross: optionalBoolean(body, 'kdj_golden_cross'),
    boll_bandwidth_max: optionalNumber(body, 'boll_bandwidth_max'),
    volume_ratio_min: optionalNumber(body, 'volume_ratio_min'),
  }
  if (Object.values(filters).every((value) => value === null || value === false)) {
    throw new HttpError(422, '请至少选择一个筛选条件')
  }
  if (
    filters.price_min !== null &&
    filters.price_max !== null &&
    filters.price_min > filters.price_max
  ) {
    throw new HttpError(400, '最低价格不能高于最高价格')
  }
  return filters
}

async function boardRows(env: Env, market: Market): Promise<BoardRow[]> {
  const row = await env.DB
    .prepare('SELECT payload_json FROM market_home_boards WHERE market = ?')
    .bind(market)
    .first<{ payload_json: string }>()
  if (!row) throw new HttpError(503, '市场行情池尚未初始化')
  const parsed = JSON.parse(row.payload_json) as { rows?: BoardRow[] }
  return parsed.rows ?? []
}

function spotPass(row: BoardRow, filters: Filters): boolean {
  return !(
    (filters.price_min !== null && row.last_price < filters.price_min) ||
    (filters.price_max !== null && row.last_price > filters.price_max) ||
    (filters.change_pct_min !== null && row.change_pct < filters.change_pct_min) ||
    (filters.change_pct_max !== null && row.change_pct > filters.change_pct_max)
  )
}

function needsTechnical(filters: Filters): boolean {
  return (
    filters.rsi_min !== null ||
    filters.rsi_max !== null ||
    filters.ma_bull_aligned ||
    filters.macd_golden_cross ||
    filters.kdj_golden_cross ||
    filters.boll_bandwidth_max !== null ||
    filters.volume_ratio_min !== null
  )
}

function yahooSymbol(row: BoardRow): string {
  if (row.market === 'us') return row.symbol
  if (row.market === 'hk') {
    return `${row.symbol.replace(/^0+/u, '').padStart(4, '0')}.HK`
  }
  return `${row.symbol}.${row.symbol.startsWith('6') ? 'SS' : 'SZ'}`
}

async function candles(row: BoardRow): Promise<Candle[]> {
  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol(row))}`,
  )
  url.searchParams.set('range', '1y')
  url.searchParams.set('interval', '1d')
  url.searchParams.set('events', 'history')
  const response = await fetch(url, {
    headers: { 'user-agent': 'Midas-Trading-Cloudflare/1.0' },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const payload = (await response.json()) as {
    chart?: {
      result?: Array<{
        indicators?: {
          quote?: Array<{
            high?: Array<number | null>
            low?: Array<number | null>
            close?: Array<number | null>
            volume?: Array<number | null>
          }>
        }
      }>
    }
  }
  const quote = payload.chart?.result?.[0]?.indicators?.quote?.[0]
  return (quote?.close ?? []).flatMap((close, index) => {
    const high = quote?.high?.[index]
    const low = quote?.low?.[index]
    const volume = quote?.volume?.[index]
    if (
      typeof close !== 'number' ||
      typeof high !== 'number' ||
      typeof low !== 'number' ||
      !Number.isFinite(close) ||
      !Number.isFinite(high) ||
      !Number.isFinite(low)
    ) {
      return []
    }
    return [{
      close,
      high,
      low,
      volume:
        typeof volume === 'number' && Number.isFinite(volume) ? volume : 0,
    }]
  })
}

function average(values: number[]): number | null {
  return values.length > 0
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : null
}

function movingAverage(values: number[], period: number): number | null {
  return values.length >= period ? average(values.slice(-period)) : null
}

function rsi(values: number[], period = 14): number | null {
  if (values.length <= period) return null
  let gains = 0
  let losses = 0
  for (let index = values.length - period; index < values.length; index += 1) {
    const change = values[index]! - values[index - 1]!
    if (change >= 0) gains += change
    else losses -= change
  }
  if (losses === 0) return gains > 0 ? 100 : 50
  const relativeStrength = gains / losses
  return 100 - 100 / (1 + relativeStrength)
}

function emaSeries(values: number[], period: number): number[] {
  if (values.length === 0) return []
  const multiplier = 2 / (period + 1)
  const output = [values[0]!]
  for (let index = 1; index < values.length; index += 1) {
    output.push(values[index]! * multiplier + output[index - 1]! * (1 - multiplier))
  }
  return output
}

function macdGolden(values: number[]): boolean {
  if (values.length < 35) return false
  const fast = emaSeries(values, 12)
  const slow = emaSeries(values, 26)
  const diff = fast.map((value, index) => value - slow[index]!)
  const signal = emaSeries(diff, 9)
  return (
    diff.at(-2)! <= signal.at(-2)! &&
    diff.at(-1)! > signal.at(-1)!
  )
}

function kdjGolden(rows: Candle[]): boolean {
  if (rows.length < 11) return false
  let k = 50
  let d = 50
  let previousK = k
  let previousD = d
  for (let index = 8; index < rows.length; index += 1) {
    const window = rows.slice(index - 8, index + 1)
    const high = Math.max(...window.map((row) => row.high))
    const low = Math.min(...window.map((row) => row.low))
    const rsv = high > low ? ((rows[index]!.close - low) / (high - low)) * 100 : 50
    previousK = k
    previousD = d
    k = (2 * k + rsv) / 3
    d = (2 * d + k) / 3
  }
  return previousK <= previousD && k > d
}

function technical(row: BoardRow, rows: Candle[]) {
  const closes = rows.map((item) => item.close)
  const volumes = rows.map((item) => item.volume)
  const ma5 = movingAverage(closes, 5)
  const ma20 = movingAverage(closes, 20)
  const ma60 = movingAverage(closes, 60)
  const mid = ma20
  const deviation =
    mid === null
      ? null
      : Math.sqrt(
          closes
            .slice(-20)
            .reduce((sum, value) => sum + (value - mid) ** 2, 0) / 20,
        )
  const bandwidth =
    mid && deviation !== null ? ((4 * deviation) / mid) * 100 : null
  const volumeAverage = movingAverage(volumes.slice(0, -1), 20)
  const volumeRatio =
    volumeAverage && volumeAverage > 0 ? volumes.at(-1)! / volumeAverage : 0
  return {
    symbol: row.symbol,
    name: row.name,
    last_price: row.last_price,
    change_pct: row.change_pct,
    rsi_14: rsi(closes),
    ma_5: ma5,
    ma_20: ma20,
    ma_60: ma60,
    macd_golden: macdGolden(closes),
    kdj_golden: kdjGolden(rows),
    boll_bandwidth: bandwidth,
    volume_ratio: volumeRatio,
  }
}

function technicalPass(
  hit: ReturnType<typeof technical>,
  filters: Filters,
): boolean {
  return !(
    (filters.rsi_min !== null && (hit.rsi_14 === null || hit.rsi_14 < filters.rsi_min)) ||
    (filters.rsi_max !== null && (hit.rsi_14 === null || hit.rsi_14 > filters.rsi_max)) ||
    (filters.ma_bull_aligned &&
      (hit.ma_5 === null ||
        hit.ma_20 === null ||
        hit.ma_60 === null ||
        !(hit.ma_5 > hit.ma_20 && hit.ma_20 > hit.ma_60))) ||
    (filters.macd_golden_cross && !hit.macd_golden) ||
    (filters.kdj_golden_cross && !hit.kdj_golden) ||
    (filters.boll_bandwidth_max !== null &&
      (hit.boll_bandwidth === null ||
        hit.boll_bandwidth > filters.boll_bandwidth_max)) ||
    (filters.volume_ratio_min !== null &&
      hit.volume_ratio < filters.volume_ratio_min)
  )
}

async function screenedRows(
  rows: BoardRow[],
  filters: Filters,
): Promise<Array<ReturnType<typeof technical>>> {
  const spot = rows.filter((row) => spotPass(row, filters))
  if (!needsTechnical(filters)) {
    return spot.map((row) => ({
      symbol: row.symbol,
      name: row.name,
      last_price: row.last_price,
      change_pct: row.change_pct,
      rsi_14: null,
      ma_5: null,
      ma_20: null,
      ma_60: null,
      macd_golden: false,
      kdj_golden: false,
      boll_bandwidth: null,
      volume_ratio: 0,
    }))
  }
  const settled = await Promise.allSettled(
    spot.map(async (row) => technical(row, await candles(row))),
  )
  return settled.flatMap((result) =>
    result.status === 'fulfilled' && technicalPass(result.value, filters)
      ? [result.value]
      : [],
  )
}

export async function handleScreenerRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (!path.startsWith('/api/v1/screener/')) return null
  const match = path.match(/^\/api\/v1\/screener\/(cn|us|hk)$/u)
  if (!match?.[1]) {
    return jsonResponse({ detail: 'Route not found' }, 404, requestId, request.method)
  }
  if (request.method !== 'POST') {
    return jsonResponse({ detail: 'Method not allowed' }, 405, requestId, request.method)
  }
  const market = match[1] as Market
  const filters = parseFilters(await readJsonObject(request))
  const url = new URL(request.url)
  const page = Math.max(1, Number.parseInt(url.searchParams.get('page') ?? '1', 10) || 1)
  const pageSize = Math.min(
    50,
    Math.max(1, Number.parseInt(url.searchParams.get('page_size') ?? '30', 10) || 30),
  )
  const rows = await boardRows(env, market)
  const hits = await screenedRows(rows, filters)
  const start = (page - 1) * pageSize
  return jsonResponse(
    {
      market,
      total: hits.length,
      page,
      page_size: pageSize,
      scanned: rows.length,
      candidate_capped: true,
      hits: hits.slice(start, start + pageSize).map((hit) => ({
        ...hit,
        macd_golden: filters.macd_golden_cross ? hit.macd_golden : null,
        kdj_golden: filters.kdj_golden_cross ? hit.kdj_golden : null,
        boll_bandwidth:
          filters.boll_bandwidth_max !== null ? hit.boll_bandwidth : null,
        volume_ratio:
          filters.volume_ratio_min !== null ? hit.volume_ratio : null,
      })),
      disclaimer:
        '以上为独立行情重点池中符合所选条件的客观列表，并非全市场扫描；仅供参考，不构成投资建议。',
    },
    200,
    requestId,
    request.method,
  )
}
