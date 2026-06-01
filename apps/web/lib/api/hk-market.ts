/**
 * 港股榜单 / 情绪 API client(港股首页全市场)。
 *
 * GET /api/v1/hk/board · 情绪条(涨跌平家数 + 总成交额 · ★港股无涨跌停)+ 涨幅/跌幅/成交额 3 榜。
 * ★ 数据 = 新浪源【主要成分股】(限页前 15 页 ≈ 900 只 · 非全市场 2764)· 只读。
 * 板块暂不做(港股全市场无现成行业源 · 对比 cn 的 sectors)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface HkSpotRow {
  symbol: string // 5 位港股代码 '00700'
  name: string
  last_price: number
  change_pct: number // %(可负)
  change_amount: number
  amount: number // 成交额(港币元)
  volume: number
}

export interface HkBreadth {
  ts: string
  up_count: number
  down_count: number
  flat_count: number
  total_amount: number // 主要成分股总成交额(港币元)· ★港股无涨跌停 → 无 limit 字段
}

export interface HkBoardResponse {
  breadth: HkBreadth | null
  data_as_of: string | null
  gainers: HkSpotRow[]
  losers: HkSpotRow[]
  top_amount: HkSpotRow[]
  // ★ 无 sectors:港股全市场无现成行业源(对比 CnBoardResponse)· 留后续
}

export class HkMarketApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`HkMarketApi ${status}: ${detail}`)
    this.name = 'HkMarketApiError'
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { signal })
  if (!r.ok) {
    let detail = `HTTP ${r.status}`
    try {
      const body = (await r.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* ignore */
    }
    throw new HkMarketApiError(r.status, detail)
  }
  return (await r.json()) as T
}

/** 港股榜单 + 情绪条(主要成分股)· limit 默认 900 = 数据池全量 · 供前端滚动加载到底。 */
export function fetchHkBoard(limit = 900, signal?: AbortSignal): Promise<HkBoardResponse> {
  return getJson<HkBoardResponse>(`/api/v1/hk/board?limit=${limit}`, signal)
}
