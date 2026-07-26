/**
 * 选股筛选器 API client · 股票第一批 功能1 · 1a(只读 · 公开端点 · 非荐股)。
 *
 * 红线:结果是"符合条件的标的"客观列表 + 免责(disclaimer 由后端返回),非荐股。
 * 公开只读端点(同榜单)· 不带 token。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export type StockMarket = 'cn' | 'us' | 'hk'

export interface ScreenerFilters {
  price_min?: number | null
  price_max?: number | null
  change_pct_min?: number | null
  change_pct_max?: number | null
  rsi_min?: number | null
  rsi_max?: number | null
  ma_bull_aligned?: boolean | null
  macd_golden_cross?: boolean | null
  kdj_golden_cross?: boolean | null
  boll_bandwidth_max?: number | null
  volume_ratio_min?: number | null
}

export interface ScreenerHit {
  symbol: string
  name: string
  last_price: number
  change_pct: number
  rsi_14: number | null
  ma_5: number | null
  ma_20: number | null
  ma_60: number | null
  macd_golden: boolean | null
  kdj_golden: boolean | null
  boll_bandwidth: number | null
  volume_ratio: number | null
}

export interface ScreenerResponse {
  market: string
  total: number
  page: number
  page_size: number
  scanned: number
  candidate_capped: boolean
  hits: ScreenerHit[]
  disclaimer: string
}

export async function runScreener(
  market: StockMarket,
  filters: ScreenerFilters,
  page = 1,
  pageSize = 30,
  signal?: AbortSignal,
): Promise<ScreenerResponse> {
  const r = await fetch(
    `${API_BASE}/api/v1/screener/${market}?page=${page}&page_size=${pageSize}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filters),
      signal,
    },
  )
  if (!r.ok) {
    throw new Error(`筛选失败(${r.status})`)
  }
  return r.json() as Promise<ScreenerResponse>
}
