/**
 * 美股榜单 / 行业·中概板块 API client(0023 阶段③ · 3.3)。
 *
 * GET /api/v1/us/board · 全市场涨幅/跌幅/成交额 3 榜 + 行业板块。
 */

import { fetchWithRetry } from './fetch-with-retry'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

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
  const r = await fetchWithRetry(`${API_BASE}${path}`, { signal })
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

/**
 * 美股全市场榜单 + 行业板块(一次取齐)。
 */
export function fetchUsBoard(limit = 128, signal?: AbortSignal): Promise<UsBoardResponse> {
  return getJson<UsBoardResponse>(`/api/v1/us/board?limit=${limit}`, signal)
}

export function searchUsSpot(
  query: string,
  limit = 50,
  signal?: AbortSignal,
): Promise<UsSpotRow[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  return getJson<UsSpotRow[]>(`/api/v1/us/search?${params.toString()}`, signal)
}
