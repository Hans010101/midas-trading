import { HttpError, jsonResponse } from './http'

type Market = 'cn' | 'us' | 'hk'

type AssetConfig = Readonly<{
  symbol: string
  name: string
  market: Market
  sector: string
}>

type SpotQuote = AssetConfig &
  Readonly<{
    last_price: number
    prev_close: number
    change_amount: number
    change_pct: number
    amount: number
    volume: number
    quoted_at: number
  }>

type BoardSnapshot = Readonly<{
  market: Market
  rows: SpotQuote[]
  quoted_at: number
}>

const ASSETS: readonly AssetConfig[] = [
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

const INDEX_ORDER: Readonly<Record<Market, string[]>> = {
  cn: ['000001.SS', '399001.SZ', '000300.SS'],
  us: ['^DJI', '^IXIC', '^GSPC', '^RUT'],
  hk: ['^HSI', '^HSCE'],
}

function yahooSymbol(asset: AssetConfig): string {
  if (asset.market === 'us') return asset.symbol
  if (asset.market === 'hk') {
    return `${asset.symbol.replace(/^0+/u, '').padStart(4, '0')}.HK`
  }
  return `${asset.symbol}.${asset.symbol.startsWith('6') ? 'SS' : 'SZ'}`
}

function finitePositive(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? value
    : null
}

async function fetchSpotQuote(asset: AssetConfig): Promise<SpotQuote | null> {
  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol(asset))}`,
  )
  url.searchParams.set('range', '5d')
  url.searchParams.set('interval', '1d')
  const response = await fetch(url, {
    headers: { 'user-agent': 'Midas-Trading-Cloudflare/1.0' },
    signal: AbortSignal.timeout(8_000),
  })
  if (!response.ok) throw new Error(`${asset.symbol}: HTTP ${response.status}`)
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
        indicators?: {
          quote?: Array<{
            close?: Array<number | null>
            volume?: Array<number | null>
          }>
        }
      }>
    }
  }
  const chart = payload.chart?.result?.[0]
  const closes =
    chart?.indicators?.quote?.[0]?.close?.filter(
      (value): value is number =>
        typeof value === 'number' && Number.isFinite(value),
    ) ?? []
  const volumes =
    chart?.indicators?.quote?.[0]?.volume?.filter(
      (value): value is number =>
        typeof value === 'number' && Number.isFinite(value) && value >= 0,
    ) ?? []
  const last =
    finitePositive(chart?.meta?.regularMarketPrice) ??
    finitePositive(closes.at(-1))
  const previous =
    finitePositive(chart?.meta?.chartPreviousClose) ??
    finitePositive(chart?.meta?.previousClose) ??
    finitePositive(closes.at(-2))
  if (last === null || previous === null) return null
  const volume = volumes.at(-1) ?? 0
  const change = last - previous
  return {
    ...asset,
    last_price: last,
    prev_close: previous,
    change_amount: change,
    change_pct: (change / previous) * 100,
    amount: last * volume,
    volume,
    quoted_at:
      (chart?.meta?.regularMarketTime ??
        chart?.timestamp?.at(-1) ??
        Math.floor(Date.now() / 1_000)) * 1_000,
  }
}

async function settledMap<T, R>(
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

export async function refreshMarketBoard(
  env: Env,
  market: Market,
): Promise<BoardSnapshot> {
  const assets = ASSETS.filter((asset) => asset.market === market)
  const results = await settledMap(assets, 6, fetchSpotQuote)
  const rows = results.flatMap((result) =>
    result.status === 'fulfilled' && result.value ? [result.value] : [],
  )
  if (rows.length === 0) throw new Error(`${market} board refresh returned no data`)
  const quotedAt = Math.max(...rows.map((row) => row.quoted_at))
  const snapshot = { market, rows, quoted_at: quotedAt }
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
      failed: results.length - rows.length,
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

function breadth(rows: SpotQuote[], market: 'cn' | 'hk') {
  const output = {
    ts: new Date(
      Math.max(...rows.map((row) => row.quoted_at)),
    ).toISOString(),
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
      breadth: breadth(snapshot.rows, market),
      data_as_of: dataAsOf,
      pool_size: snapshot.rows.length,
      scope_label: market === 'cn' ? '重点标的池' : '活跃精选池',
      gainers: gainers.map(mapRow),
      losers: losers.map(mapRow),
      top_amount: topAmount.map(mapRow),
      ...(market === 'cn'
        ? { sectors: aggregateSectors(snapshot.rows) }
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

async function searchCn(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const params = new URL(request.url).searchParams
  const query = (params.get('q') ?? '').trim().toLowerCase()
  const limit = Number(params.get('limit') ?? '30')
  if (!query || query.length > 32) throw new HttpError(422, 'q 格式无效')
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 50) {
    throw new HttpError(422, 'limit 格式无效')
  }
  const snapshot = await readBoard(env, 'cn')
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
  if (path === '/api/v1/cn/search' && request.method === 'GET') {
    return searchCn(request, env, requestId)
  }
  return null
}
