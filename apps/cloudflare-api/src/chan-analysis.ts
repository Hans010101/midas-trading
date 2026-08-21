import { HttpError, jsonResponse } from './http'
import { fetchMarketKlines, type Kline } from './market'

type Fractal = Readonly<{
  ts: string
  price: number
  kind: 'G' | 'D'
  index: number
}>

function fractals(items: Kline[]): Fractal[] {
  const result: Fractal[] = []
  for (let index = 2; index < items.length - 2; index += 1) {
    const current = items[index]!
    const window = items.slice(index - 2, index + 3)
    const top = window.every((item) => current.high >= item.high)
    const bottom = window.every((item) => current.low <= item.low)
    if (!top && !bottom) continue
    const candidate: Fractal = {
      ts: current.ts,
      price: top ? current.high : current.low,
      kind: top ? 'G' : 'D',
      index,
    }
    const previous = result.at(-1)
    if (previous?.kind === candidate.kind) {
      const moreExtreme = candidate.kind === 'G'
        ? candidate.price > previous.price
        : candidate.price < previous.price
      if (moreExtreme) result[result.length - 1] = candidate
    } else if (!previous || candidate.index - previous.index >= 4) {
      result.push(candidate)
    }
  }
  return result
}

function buildBis(points: Fractal[]) {
  return points.slice(1).map((point, index) => {
    const start = points[index]!
    const direction = point.price >= start.price ? 'up' : 'down'
    return {
      start_ts: start.ts,
      end_ts: point.ts,
      start_price: start.price,
      end_price: point.price,
      direction,
      high: Math.max(start.price, point.price),
      low: Math.min(start.price, point.price),
      power: Math.abs(point.price - start.price),
      length: point.index - start.index,
    }
  })
}

function buildZhongshus(bis: ReturnType<typeof buildBis>) {
  const result: Array<Readonly<{
    start_ts: string
    end_ts: string
    high: number
    low: number
  }>> = []
  for (let index = 0; index <= bis.length - 3; index += 1) {
    const window = bis.slice(index, index + 3)
    const high = Math.min(...window.map((item) => item.high))
    const low = Math.max(...window.map((item) => item.low))
    if (high > low) {
      const last = result.at(-1)
      const item = {
        start_ts: window[0]!.start_ts,
        end_ts: window.at(-1)!.end_ts,
        high,
        low,
      }
      if (!last || item.start_ts > last.end_ts) result.push(item)
    }
  }
  return result
}

function buildSegments(bis: ReturnType<typeof buildBis>) {
  const segments: Array<Readonly<{
    start_ts: string
    end_ts: string
    direction: 'up' | 'down'
    high: number
    low: number
    bi_count: number
  }>> = []
  for (let index = 0; index <= bis.length - 3; index += 2) {
    const window = bis.slice(index, index + 3)
    if (window.length < 3) continue
    const first = window[0]!
    const last = window[2]!
    const direction = last.end_price >= first.start_price ? 'up' : 'down'
    const candidate = {
      start_ts: first.start_ts,
      end_ts: last.end_ts,
      direction,
      high: Math.max(...window.map((item) => item.high)),
      low: Math.min(...window.map((item) => item.low)),
      bi_count: window.length,
    } as const
    const previous = segments.at(-1)
    if (previous?.direction === candidate.direction) {
      segments[segments.length - 1] = {
        ...candidate,
        start_ts: previous.start_ts,
        high: Math.max(previous.high, candidate.high),
        low: Math.min(previous.low, candidate.low),
        bi_count: previous.bi_count + candidate.bi_count - 1,
      }
    } else segments.push(candidate)
  }
  return segments
}

function structureSummary(
  items: Kline[],
  bis: ReturnType<typeof buildBis>,
  zhongshus: ReturnType<typeof buildZhongshus>,
) {
  const recent = bis.slice(-5)
  const last = items.at(-1)!
  const trend = recent.length >= 3 && recent.at(-1)!.end_price > recent[0]!.start_price
    ? 'up'
    : recent.length >= 3 && recent.at(-1)!.end_price < recent[0]!.start_price
      ? 'down'
      : 'range'
  const current = zhongshus.at(-1) ?? null
  const location = !current ? 'outside'
    : last.close > current.high ? 'above'
      : last.close < current.low ? 'below' : 'inside'
  return {
    trend,
    location,
    latest_close: last.close,
    current_zhongshu: current,
    confirmed_bis: bis.length,
    data_quality: items.length >= 200 && bis.length >= 6 ? 'good' : 'limited',
  }
}

function buySellPoints(
  bis: ReturnType<typeof buildBis>,
  zhongshus: ReturnType<typeof buildZhongshus>,
) {
  const result: Array<Readonly<{
    ts: string
    price: number
    kind: 'B1' | 'B2' | 'B3' | 'S1' | 'S2' | 'S3'
    description: string
  }>> = []
  if (bis.length < 3 || zhongshus.length === 0) return result
  for (const zhongshu of zhongshus) {
    for (let index = 0; index < bis.length - 1; index += 1) {
      const current = bis[index]!
      const next = bis[index + 1]!
      if (current.start_ts < zhongshu.end_ts) continue
      if (current.direction === 'up' && current.end_price > zhongshu.high &&
          next.direction === 'down' && next.end_price >= zhongshu.high) {
        result.push({ ts: next.end_ts, price: next.end_price, kind: 'B3',
          description: `三买 · 突破中枢(${zhongshu.high.toFixed(2)})后回踩不破上沿` })
        break
      }
      if (current.direction === 'down' && current.end_price < zhongshu.low &&
          next.direction === 'up' && next.end_price <= zhongshu.low) {
        result.push({ ts: next.end_ts, price: next.end_price, kind: 'S3',
          description: `三卖 · 跌破中枢(${zhongshu.low.toFixed(2)})后反弹不破下沿` })
        break
      }
    }
  }
  const recent = bis.slice(-5)
  const last = zhongshus.at(-1)!
  for (let index = 0; index < recent.length; index += 1) {
    const current = recent[index]!
    if (current.direction === 'down' && current.end_price < last.low) {
      result.push({ ts: current.end_ts, price: current.end_price, kind: 'B1',
        description: `一买 · 跌破中枢下沿(${last.low.toFixed(2)})后底背离` })
      const second = recent[index + 2]
      if (recent[index + 1]?.direction === 'up' && second?.direction === 'down' &&
          second.end_price > current.end_price) {
        result.push({ ts: second.end_ts, price: second.end_price, kind: 'B2',
          description: '二买 · 一买后回踩不破前低' })
      }
      break
    }
    if (current.direction === 'up' && current.end_price > last.high) {
      result.push({ ts: current.end_ts, price: current.end_price, kind: 'S1',
        description: `一卖 · 突破中枢上沿(${last.high.toFixed(2)})后顶背离` })
      const second = recent[index + 2]
      if (recent[index + 1]?.direction === 'down' && second?.direction === 'up' &&
          second.end_price < current.end_price) {
        result.push({ ts: second.end_ts, price: second.end_price, kind: 'S2',
          description: '二卖 · 一卖后反弹不破前高' })
      }
      break
    }
  }
  return result.sort((left, right) => left.ts.localeCompare(right.ts)).slice(-30)
}

export function analyzeChanItems(items: Kline[]) {
  const points = fractals(items)
  const bis = buildBis(points)
  const zhongshus = buildZhongshus(bis)
  return {
    fractals: points.map(({ index: _index, ...point }) => point),
    bis,
    segments: buildSegments(bis),
    zhongshus,
    buy_sell_points: buySellPoints(bis, zhongshus),
    structure: structureSummary(items, bis, zhongshus),
  }
}

export async function handleChanAnalysisRoute(
  request: Request,
  requestId: string,
): Promise<Response | null> {
  const url = new URL(request.url)
  if (url.pathname !== '/api/v1/analysis/chan') return null
  if (request.method !== 'GET') {
    return jsonResponse({ detail: 'Method not allowed' }, 405, requestId, request.method)
  }
  const symbol = url.searchParams.get('symbol')?.trim() ?? ''
  const market = url.searchParams.get('market') ?? ''
  const period = url.searchParams.get('period') ?? '1h'
  const instrument = url.searchParams.get('instrument') === 'perp' ? 'perp' : 'spot'
  const limit = Math.min(Math.max(Number(url.searchParams.get('limit') ?? 300), 80), 1_000)
  if (!symbol || !['cn', 'us', 'hk', 'crypto'].includes(market)) {
    throw new HttpError(400, 'symbol 或 market 格式无效')
  }
  const result = await fetchMarketKlines({ symbol, market, period, instrument, limit })
  if (result.items.length < 20) throw new HttpError(404, '有效 K 线不足，无法生成缠论结构')
  const analysis = analyzeChanItems(result.items)
  return jsonResponse(
    {
      symbol,
      market,
      period,
      bar_count: result.items.length,
      ...analysis,
      disclaimer: '',
      source: result.source,
      data_as_of: result.items.at(-1)?.ts ?? null,
    },
    200,
    requestId,
    request.method,
  )
}
