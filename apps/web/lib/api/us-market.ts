/**
 * 美股榜单 / 行业·中概板块 API client(0023 阶段③ · 3.3)。
 *
 * GET /api/v1/us/board · 策展池(重点关注池 · 非全市场)内 涨幅/跌幅/成交额 3 榜 +
 * 行业板块 + 中概股板块。数据 yfinance 批量 · 只读 · 成交额为美元估(close×volume)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface UsSpotRow {
  symbol: string
  name: string
  sector: string
  last_price: number
  change_pct: number
  amount: number // 美元估
  volume: number
}

export interface UsSector {
  name: string
  change_pct: number
  stock_count: number
  total_amount: number
}

export interface UsBoardResponse {
  data_as_of: string | null
  pool_size: number
  gainers: UsSpotRow[]
  losers: UsSpotRow[]
  top_amount: UsSpotRow[]
  sectors: UsSector[]
}

export class UsMarketApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`UsMarketApi ${status}: ${detail}`)
    this.name = 'UsMarketApiError'
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
    throw new UsMarketApiError(r.status, detail)
  }
  return (await r.json()) as T
}

/** 美股重点关注池榜单 + 行业/中概板块(一次取齐)。 */
export function fetchUsBoard(signal?: AbortSignal): Promise<UsBoardResponse> {
  return getJson<UsBoardResponse>('/api/v1/us/board', signal)
}
