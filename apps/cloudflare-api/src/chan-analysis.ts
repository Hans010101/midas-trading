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

function buySellPoints(
  points: Fractal[],
  bis: ReturnType<typeof buildBis>,
) {
  const result: Array<Readonly<{
    ts: string
    price: number
    kind: 'B1' | 'B2' | 'B3' | 'S1' | 'S2' | 'S3'
    description: string
  }>> = []
  for (let index = 2; index < points.length; index += 1) {
    const point = points[index]!
    const previousSame = points[index - 2]!
    const recentBi = bis[index - 1]
    if (!recentBi) continue
    if (point.kind === 'D' && point.price > previousSame.price) {
      result.push({
        ts: point.ts,
        price: point.price,
        kind: 'B2',
        description: '底分型抬高，次级别回撤未创新低',
      })
    }
    if (point.kind === 'G' && point.price < previousSame.price) {
      result.push({
        ts: point.ts,
        price: point.price,
        kind: 'S2',
        description: '顶分型降低，次级别反弹未创新高',
      })
    }
    const priorPower = bis[index - 3]?.power
    if (priorPower && recentBi.power < priorPower * 0.7) {
      result.push({
        ts: point.ts,
        price: point.price,
        kind: point.kind === 'D' ? 'B1' : 'S1',
        description: '同向笔力度明显衰减，出现背驰候选',
      })
    }
  }
  return result.slice(-30)
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
  const points = fractals(result.items)
  const bis = buildBis(points)
  return jsonResponse(
    {
      symbol,
      market,
      period,
      bar_count: result.items.length,
      fractals: points.map(({ index: _index, ...point }) => point),
      bis,
      zhongshus: buildZhongshus(bis),
      buy_sell_points: buySellPoints(points, bis),
      disclaimer: '',
      source: result.source,
      data_as_of: result.items.at(-1)?.ts ?? null,
    },
    200,
    requestId,
    request.method,
  )
}
