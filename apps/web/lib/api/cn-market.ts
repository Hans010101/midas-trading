/**
 * A股榜单 / 情绪 / 行业板块 API client(0023 阶段③ · 3.2)。
 *
 * GET /api/v1/cn/board · 一次取:情绪条 + 涨幅/跌幅/成交额 3 榜 + 行业板块。
 * 数据 Sina 源 · 只读。换手率/量比本期界面不体现(Sina 无字段 · 东财不可达)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface CnSpotRow {
  symbol: string // 纯代码 '600519'
  name: string
  last_price: number
  change_pct: number // %(可负)
  change_amount: number
  amount: number // 成交额(元)
  volume: number
}

export interface CnBreadth {
  ts: string
  up_count: number
  down_count: number
  flat_count: number
  limit_up_count: number // 估算
  limit_down_count: number // 估算
  total_amount: number // 两市总成交额(元)
}

export interface CnSector {
  name: string
  change_pct: number
  stock_count: number
  total_amount: number
  leader_name: string
  leader_change_pct: number
}

export interface CnBoardResponse {
  breadth: CnBreadth | null
  data_as_of: string | null
  gainers: CnSpotRow[]
  losers: CnSpotRow[]
  top_amount: CnSpotRow[]
  sectors: CnSector[]
}

export class CnMarketApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`CnMarketApi ${status}: ${detail}`)
    this.name = 'CnMarketApiError'
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
    throw new CnMarketApiError(r.status, detail)
  }
  return (await r.json()) as T
}

/** A股榜单 + 情绪条 + 行业板块(一次取齐)。 */
export function fetchCnBoard(signal?: AbortSignal): Promise<CnBoardResponse> {
  return getJson<CnBoardResponse>('/api/v1/cn/board', signal)
}
