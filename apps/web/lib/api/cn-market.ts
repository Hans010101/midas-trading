/**
 * A股榜单 / 情绪 / 行业板块 API client(0023 阶段③ · 3.2)。
 *
 * GET /api/v1/cn/board · 一次取:情绪条 + 涨幅/跌幅/成交额 3 榜 + 行业板块。
 * 数据 Sina 源 · 只读。换手率/量比本期界面不体现(Sina 无字段 · 东财不可达)。
 */

import { fetchWithRetry } from './fetch-with-retry'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

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
  pool_size?: number
  scope_label?: string
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
  const r = await fetchWithRetry(`${API_BASE}${path}`, { signal })
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

/** A股榜单 + 情绪条 + 行业板块(一次取齐)· limit 默认 100 = 各榜显示前 100。 */
export function fetchCnBoard(limit = 100, signal?: AbortSignal): Promise<CnBoardResponse> {
  return getJson<CnBoardResponse>(`/api/v1/cn/board?limit=${limit}`, signal)
}

/**
 * A股全市场搜索(代码 / 中文名 · 覆盖全 ~5500)。
 * 走后端 /cn/search(查 cn_spot_snapshot 全市场快照)· 返带价/涨跌的行,可直接渲染 + 点进详情。
 */
export function searchCnSpot(q: string, limit = 30, signal?: AbortSignal): Promise<CnSpotRow[]> {
  return getJson<CnSpotRow[]>(
    `/api/v1/cn/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    signal,
  )
}
