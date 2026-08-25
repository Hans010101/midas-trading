import { HttpError, jsonResponse } from './http'

type Market = 'cn' | 'us' | 'hk'

type AssetMeta = Readonly<{
  symbol: string
  name: string
  market: Market
  sector: string
}>

type SpotQuote = Readonly<{
  symbol: string
  name: string
  sector: string
  last_price: number
  prev_close: number
  change_amount: number
  change_pct: number
  amount: number
  volume: number
}>

type SectorSummary = Readonly<{
  name: string
  change_pct: number
  stock_count: number
  total_amount: number
  leader_name: string
  leader_change_pct: number
}>

type BoardSnapshot = Readonly<{
  market: Market
  rows: SpotQuote[]
  quoted_at: number
  sectors?: SectorSummary[]
}>

const KNOWN_ASSETS: readonly AssetMeta[] = [
  { symbol: '600519', name: '贵州茅台', market: 'cn', sector: '消费' },
  { symbol: '601318', name: '中国平安', market: 'cn', sector: '金融' },
  { symbol: '600036', name: '招商银行', market: 'cn', sector: '金融' },
  { symbol: '000001', name: '平安银行', market: 'cn', sector: '金融' },
  { symbol: '000858', name: '五粮液', market: 'cn', sector: '消费' },
  { symbol: '300750', name: '宁德时代', market: 'cn', sector: '新能源' },
  { symbol: '002594', name: '比亚迪', market: 'cn', sector: '新能源' },
  { symbol: '000333', name: '美的集团', market: 'cn', sector: '家电' },
  { symbol: '300059', name: '东方财富', market: 'cn', sector: '金融科技' },
  { symbol: '601398', name: '工商银行', market: 'cn', sector: '金融' },
  { symbol: '601857', name: '中国石油', market: 'cn', sector: '能源' },
  { symbol: '600276', name: '恒瑞医药', market: 'cn', sector: '医药' },
  { symbol: 'AAPL', name: '苹果', market: 'us', sector: '科技' },
  { symbol: 'MSFT', name: '微软', market: 'us', sector: '科技' },
  { symbol: 'NVDA', name: '英伟达', market: 'us', sector: '半导体' },
  { symbol: 'GOOGL', name: '谷歌', market: 'us', sector: '互联网' },
  { symbol: 'AMZN', name: '亚马逊', market: 'us', sector: '消费' },
  { symbol: 'TSLA', name: '特斯拉', market: 'us', sector: '汽车' },
  { symbol: 'META', name: 'Meta', market: 'us', sector: '互联网' },
  { symbol: 'AMD', name: 'AMD', market: 'us', sector: '半导体' },
  { symbol: 'NFLX', name: '奈飞', market: 'us', sector: '传媒' },
  { symbol: 'JPM', name: '摩根大通', market: 'us', sector: '金融' },
  { symbol: 'XOM', name: '埃克森美孚', market: 'us', sector: '能源' },
  { symbol: 'WMT', name: '沃尔玛', market: 'us', sector: '消费' },
  { symbol: 'BABA', name: '阿里巴巴', market: 'us', sector: '中概股' },
  { symbol: 'PDD', name: '拼多多', market: 'us', sector: '中概股' },
  { symbol: '00700', name: '腾讯控股', market: 'hk', sector: '互联网' },
  { symbol: '09988', name: '阿里巴巴-W', market: 'hk', sector: '互联网' },
  { symbol: '03690', name: '美团-W', market: 'hk', sector: '互联网' },
  { symbol: '01810', name: '小米集团-W', market: 'hk', sector: '科技' },
  { symbol: '00941', name: '中国移动', market: 'hk', sector: '电信' },
  { symbol: '01211', name: '比亚迪股份', market: 'hk', sector: '汽车' },
  { symbol: '00005', name: '汇丰控股', market: 'hk', sector: '金融' },
  { symbol: '00388', name: '香港交易所', market: 'hk', sector: '金融' },
  { symbol: '00939', name: '建设银行', market: 'hk', sector: '金融' },
  { symbol: '02318', name: '中国平安', market: 'hk', sector: '金融' },
  { symbol: '00883', name: '中国海洋石油', market: 'hk', sector: '能源' },
  { symbol: '01024', name: '快手-W', market: 'hk', sector: '互联网' },
  { symbol: '09618', name: '京东集团-SW', market: 'hk', sector: '互联网' },
  { symbol: '09888', name: '百度集团-SW', market: 'hk', sector: '互联网' },
]

const KNOWN_ASSET_META = new Map(
  KNOWN_ASSETS.map((asset) => [`${asset.market}:${asset.symbol}`, asset]),
)

const CN_SPOT_URL =
  'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeDataSimple?page=1&num=10000&sort=symbol&asc=1&node=hs_a&_s_r_a=page'
const CN_SECTORS_URL =
  'https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php'
const US_SPOT_URL =
  'https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true'
const HK_SPOT_URL =
  'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHKStockData'

const INDEX_ORDER: Readonly<Record<Market, string[]>> = {
  cn: ['000001.SS', '399001.SZ', '000300.SS'],
  us: ['^DJI', '^IXIC', '^GSPC', '^RUT'],
  hk: ['^HSI', '^HSCE'],
}

function numeric(value: unknown): number {
  const parsed = Number(String(value ?? '').replaceAll(',', '').replace('$', '').replace('%', ''))
  return Number.isFinite(parsed) ? parsed : 0
}

async function fetchJson<T>(url: URL | string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'user-agent': 'Mozilla/5.0 Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(30_000),
  })
  if (!response.ok) throw new Error(`market source HTTP ${response.status}`)
  return (await response.json()) as T
}

function spotQuote(
  market: Market,
  symbol: string,
  name: string,
  last: number,
  previous: number,
  change: number,
  changePct: number,
  volume: number,
  amount: number,
  sector = '',
): SpotQuote | null {
  if (!symbol || last <= 0 || !Number.isFinite(changePct)) return null
  const known = KNOWN_ASSET_META.get(`${market}:${symbol}`)
  return {
    symbol,
    name: known?.name ?? name,
    sector: known?.sector ?? sector,
    last_price: last,
    prev_close: previous > 0 ? previous : last - change,
    change_amount: change,
    change_pct: changePct,
    amount: Math.max(amount, 0),
    volume: Math.max(volume, 0),
  }
}

async function fetchCnSnapshot(): Promise<Pick<BoardSnapshot, 'rows' | 'sectors'>> {
  type SinaRow = Record<string, unknown>
  const [sourceRows, sectorResponse] = await Promise.all([
    fetchJson<SinaRow[]>(CN_SPOT_URL),
    fetch(CN_SECTORS_URL, { signal: AbortSignal.timeout(30_000) }).catch(() => null),
  ])
  const rows = sourceRows.flatMap((row) => {
    const item = spotQuote(
      'cn',
      String(row.code ?? ''),
      String(row.name ?? ''),
      numeric(row.trade),
      numeric(row.settlement),
      numeric(row.pricechange),
      numeric(row.changepercent),
      numeric(row.volume),
      numeric(row.amount),
    )
    return item ? [item] : []
  })
  let text = ''
  if (sectorResponse?.ok) {
    try {
      text = new TextDecoder('gb18030').decode(await sectorResponse.arrayBuffer())
    } catch {
      // Sector data is optional; keep the stock board available if decoding fails.
    }
  }
  const rawSectors = text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1)
  let parsedSectors: Record<string, string> = {}
  try {
    parsedSectors = rawSectors ? JSON.parse(rawSectors) as Record<string, string> : {}
  } catch {
    parsedSectors = {}
  }
  const sectors = Object.values(parsedSectors).flatMap((value) => {
    const fields = value.split(',')
    const name = fields[1]?.trim() ?? ''
    if (!name) return []
    return [{
      name,
      change_pct: numeric(fields[5]),
      stock_count: numeric(fields[2]),
      total_amount: numeric(fields[7]),
      leader_name: fields[13]?.trim() ?? '',
      leader_change_pct: numeric(fields[9]),
    }]
  })
  return { rows, sectors }
}

async function fetchUsRows(): Promise<SpotQuote[]> {
  const payload = await fetchJson<{
    data?: { rows?: Array<Record<string, unknown>> }
  }>(US_SPOT_URL)
  return (payload.data?.rows ?? []).flatMap((row) => {
    const last = numeric(row.lastsale)
    const change = numeric(row.netchange)
    const volume = numeric(row.volume)
    const item = spotQuote(
      'us',
      String(row.symbol ?? ''),
      String(row.name ?? ''),
      last,
      last - change,
      change,
      numeric(row.pctchange),
      volume,
      last * volume,
      String(row.sector ?? 'Other'),
    )
    return item ? [item] : []
  })
}

async function fetchHkRows(): Promise<SpotQuote[]> {
  type SinaRow = Record<string, unknown>
  const pages = await Promise.all(
    Array.from({ length: 15 }, (_, index) => {
      const url = new URL(HK_SPOT_URL)
      url.search = new URLSearchParams({
        page: String(index + 1),
        num: '60',
        sort: 'symbol',
        asc: '1',
        node: 'qbgg_hk',
        _s_r_a: 'init',
      }).toString()
      return fetchJson<SinaRow[]>(url)
    }),
  )
  return pages.flat().flatMap((row) => {
    const item = spotQuote(
      'hk',
      String(row.symbol ?? ''),
      String(row.name ?? ''),
      numeric(row.lasttrade),
      numeric(row.prevclose),
      numeric(row.pricechange),
      numeric(row.changepercent),
      numeric(row.volume),
      numeric(row.amount),
    )
    return item ? [item] : []
  })
}

export async function refreshMarketBoard(
  env: Env,
  market: Market,
): Promise<BoardSnapshot> {
  const source = market === 'cn'
    ? await fetchCnSnapshot()
    : { rows: market === 'us' ? await fetchUsRows() : await fetchHkRows() }
  const rows = source.rows
  if (rows.length === 0) throw new Error(`${market} board refresh returned no data`)
  const quotedAt = Date.now()
  const snapshot = {
    market,
    rows,
    quoted_at: quotedAt,
    ...('sectors' in source ? { sectors: source.sectors } : {}),
  }
  await env.DB
    .prepare(
      `INSERT INTO market_home_boards
        (market, payload_json, quoted_at, updated_at)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(market) DO UPDATE SET
         payload_json = excluded.payload_json,
         quoted_at = excluded.quoted_at,
         updated_at = excluded.updated_at`,
    )
    .bind(market, JSON.stringify(snapshot), quotedAt, Date.now())
    .run()
  console.log(
    JSON.stringify({
      event: 'market_board.refresh_complete',
      market,
      stored: rows.length,
    }),
  )
  return snapshot
}

export async function refreshMarketBoards(env: Env): Promise<void> {
  for (const market of ['cn', 'us', 'hk'] as const) {
    try {
      await refreshMarketBoard(env, market)
    } catch (error) {
      console.error(
        JSON.stringify({
          event: 'market_board.refresh_failed',
          market,
          error: error instanceof Error ? error.message : String(error),
        }),
      )
    }
  }
}

async function readBoard(
  env: Env,
  market: Market,
): Promise<BoardSnapshot> {
  const row = await env.DB
    .prepare('SELECT payload_json FROM market_home_boards WHERE market = ?')
    .bind(market)
    .first<{ payload_json: string }>()
  if (row) return JSON.parse(row.payload_json) as BoardSnapshot
  return refreshMarketBoard(env, market)
}

function aggregateSectors(rows: SpotQuote[]) {
  const grouped = new Map<string, SpotQuote[]>()
  for (const row of rows) {
    if (!row.sector) continue
    const group = grouped.get(row.sector) ?? []
    group.push(row)
    grouped.set(row.sector, group)
  }
  return Array.from(grouped, ([name, items]) => {
    const totalAmount = items.reduce((sum, item) => sum + item.amount, 0)
    const changePct =
      totalAmount > 0
        ? items.reduce(
            (sum, item) => sum + item.change_pct * item.amount,
            0,
          ) / totalAmount
        : items.reduce((sum, item) => sum + item.change_pct, 0) /
          items.length
    const leader = items.reduce((best, item) =>
      item.change_pct > best.change_pct ? item : best,
    )
    return {
      name,
      change_pct: changePct,
      stock_count: items.length,
      total_amount: totalAmount,
      leader_name: leader.name,
      leader_change_pct: leader.change_pct,
    }
  }).sort((left, right) => right.change_pct - left.change_pct)
}

function marketStatus(market: Market, dataAsOf: number) {
  const timeZone =
    market === 'us' ? 'America/New_York' : 'Asia/Shanghai'
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date())
  const weekday = parts.find((part) => part.type === 'weekday')?.value
  const hour = Number(parts.find((part) => part.type === 'hour')?.value)
  const minute = Number(parts.find((part) => part.type === 'minute')?.value)
  const minuteOfDay = hour * 60 + minute
  const weekdayOpen = weekday !== 'Sat' && weekday !== 'Sun'
  let status = 'closed'
  let label = weekdayOpen ? '已收盘' : '休市'
  let isTradingNow = false
  if (weekdayOpen && market === 'us') {
    if (minuteOfDay >= 240 && minuteOfDay < 570) {
      status = 'pre_market'
      label = '盘前'
    } else if (minuteOfDay >= 570 && minuteOfDay < 960) {
      status = 'open'
      label = '交易中'
      isTradingNow = true
    } else if (minuteOfDay >= 960 && minuteOfDay < 1_200) {
      status = 'post_market'
      label = '盘后'
    }
  } else if (weekdayOpen) {
    const morningEnd = market === 'hk' ? 720 : 690
    const afternoonEnd = market === 'hk' ? 960 : 900
    if (
      (minuteOfDay >= 570 && minuteOfDay < morningEnd) ||
      (minuteOfDay >= 780 && minuteOfDay < afternoonEnd)
    ) {
      status = 'open'
      label = '交易中'
      isTradingNow = true
    }
  }
  return {
    market,
    status,
    label,
    is_trading_now: isTradingNow,
    as_of: new Date().toISOString(),
    data_as_of: new Date(dataAsOf).toISOString(),
  }
}

async function overview(
  request: Request,
  env: Env,
  requestId: string,
  market: Market,
): Promise<Response> {
  const rows = await env.DB
    .prepare(
      `SELECT
         symbol, name, quoted_at, last_point, prev_close,
         change_point, change_pct
       FROM market_overview_quotes
       WHERE category = 'index' AND market = ?`,
    )
    .bind(market)
    .all<{
      symbol: string
      name: string
      quoted_at: number
      last_point: number
      prev_close: number
      change_point: number
      change_pct: number
    }>()
  const order = INDEX_ORDER[market]
  const indices = rows.results
    .sort(
      (left, right) =>
        order.indexOf(left.symbol) - order.indexOf(right.symbol),
    )
    .map((row) => ({
      market,
      symbol: row.symbol,
      name: row.name,
      ts: new Date(row.quoted_at).toISOString(),
      last_point: row.last_point,
      prev_close: row.prev_close,
      change_point: row.change_point,
      change_pct: row.change_pct,
    }))
  if (indices.length === 0) throw new HttpError(503, '指数快照暂不可用')
  const dataAsOf = Math.max(
    ...rows.results.map((row) => row.quoted_at),
  )
  const response = jsonResponse(
    {
      market,
      status: marketStatus(market, dataAsOf),
      indices,
    },
    200,
    requestId,
    request.method,
  )
  response.headers.set('cache-control', 'public, max-age=30, s-maxage=120')
  return response
}

function breadth(rows: SpotQuote[], market: 'cn' | 'hk', quotedAt: number) {
  const output = {
    ts: new Date(quotedAt).toISOString(),
    up_count: rows.filter((row) => row.change_pct > 0.01).length,
    down_count: rows.filter((row) => row.change_pct < -0.01).length,
    flat_count: rows.filter(
      (row) => Math.abs(row.change_pct) <= 0.01,
    ).length,
    total_amount: rows.reduce((sum, row) => sum + row.amount, 0),
  }
  return market === 'cn'
    ? {
        ...output,
        limit_up_count: rows.filter((row) => row.change_pct >= 9.8).length,
        limit_down_count: rows.filter((row) => row.change_pct <= -9.8).length,
      }
    : output
}

async function board(
  request: Request,
  env: Env,
  requestId: string,
  market: Market,
): Promise<Response> {
  const requestedLimit = Number(
    new URL(request.url).searchParams.get('limit') ?? '50',
  )
  if (
    !Number.isSafeInteger(requestedLimit) ||
    requestedLimit < 1 ||
    requestedLimit > 1_000
  ) {
    throw new HttpError(422, 'limit 格式无效')
  }
  const snapshot = await readBoard(env, market)
  const limit = Math.min(requestedLimit, snapshot.rows.length)
  const gainers = [...snapshot.rows]
    .sort((a, b) => b.change_pct - a.change_pct)
    .slice(0, limit)
  const losers = [...snapshot.rows]
    .sort((a, b) => a.change_pct - b.change_pct)
    .slice(0, limit)
  const topAmount = [...snapshot.rows]
    .sort((a, b) => b.amount - a.amount)
    .slice(0, limit)
  const dataAsOf = new Date(snapshot.quoted_at).toISOString()
  let payload: unknown
  if (market === 'us') {
    const mapRow = (row: SpotQuote) => ({
      symbol: row.symbol,
      name: row.name,
      sector: row.sector,
      last_price: row.last_price,
      change_pct: row.change_pct,
      amount: row.amount,
      volume: row.volume,
    })
    payload = {
      data_as_of: dataAsOf,
      pool_size: snapshot.rows.length,
      gainers: gainers.map(mapRow),
      losers: losers.map(mapRow),
      top_amount: topAmount.map(mapRow),
      sectors: aggregateSectors(snapshot.rows),
    }
  } else {
    const mapRow = (row: SpotQuote) => ({
      symbol: row.symbol,
      name: row.name,
      last_price: row.last_price,
      change_pct: row.change_pct,
      change_amount: row.change_amount,
      amount: row.amount,
      volume: row.volume,
    })
    payload = {
      breadth: breadth(snapshot.rows, market, snapshot.quoted_at),
      data_as_of: dataAsOf,
      pool_size: snapshot.rows.length,
      scope_label: market === 'cn' ? 'A股全市场' : '港股活跃池',
      gainers: gainers.map(mapRow),
      losers: losers.map(mapRow),
      top_amount: topAmount.map(mapRow),
      ...(market === 'cn'
        ? { sectors: snapshot.sectors ?? [] }
        : {}),
    }
  }
  const response = jsonResponse(
    payload,
    200,
    requestId,
    request.method,
  )
  response.headers.set('cache-control', 'public, max-age=30, s-maxage=120')
  return response
}

async function hkSectors(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const snapshot = await readBoard(env, 'hk')
  const response = jsonResponse(
    {
      sectors: aggregateSectors(snapshot.rows),
      data_as_of: new Date(snapshot.quoted_at).toISOString(),
    },
    200,
    requestId,
    request.method,
  )
  response.headers.set('cache-control', 'public, max-age=60, s-maxage=300')
  return response
}

async function searchMarket(
  request: Request,
  env: Env,
  requestId: string,
  market: Market,
): Promise<Response> {
  const params = new URL(request.url).searchParams
  const query = (params.get('q') ?? '').trim().toLowerCase()
  const limit = Number(params.get('limit') ?? '30')
  if (!query || query.length > 32) throw new HttpError(422, 'q 格式无效')
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 50) {
    throw new HttpError(422, 'limit 格式无效')
  }
  const snapshot = await readBoard(env, market)
  const items = snapshot.rows
    .filter(
      (row) =>
        row.symbol.toLowerCase().includes(query) ||
        row.name.toLowerCase().includes(query),
    )
    .sort((left, right) => right.amount - left.amount)
    .slice(0, limit)
    .map((row) => ({
      symbol: row.symbol,
      name: row.name,
      sector: row.sector,
      last_price: row.last_price,
      change_pct: row.change_pct,
      change_amount: row.change_amount,
      amount: row.amount,
      volume: row.volume,
    }))
  return jsonResponse(items, 200, requestId, request.method)
}

export async function handleMarketHomeRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const overviewMatch = /^\/api\/v1\/(cn|us|hk)\/overview$/u.exec(path)
  if (overviewMatch && request.method === 'GET') {
    return overview(
      request,
      env,
      requestId,
      overviewMatch[1] as Market,
    )
  }
  const boardMatch = /^\/api\/v1\/(cn|us|hk)\/board$/u.exec(path)
  if (boardMatch && request.method === 'GET') {
    return board(request, env, requestId, boardMatch[1] as Market)
  }
  if (path === '/api/v1/hk/sectors' && request.method === 'GET') {
    return hkSectors(request, env, requestId)
  }
  const searchMatch = /^\/api\/v1\/(cn|us|hk)\/search$/u.exec(path)
  if (searchMatch && request.method === 'GET') {
    return searchMarket(request, env, requestId, searchMatch[1] as Market)
  }
  return null
}
