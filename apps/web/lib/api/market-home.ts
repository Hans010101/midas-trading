/**
 * A股 / 美股 市场首页 API client(0023 阶段③ · 3.1 基建)。
 *
 * 走只读端点(后端 cn.py / us.py):
 *   GET /api/v1/cn/overview · GET /api/v1/us/overview
 * 返回:市场状态(交易时段)+ 大盘指数卡。榜单 / 板块 = 3.2 / 3.3 再加。
 *
 * 红线:接不上的字段交给页面显示空态,绝不在此伪造数据。
 */

import { fetchWithRetry } from './fetch-with-retry'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export type MarketKind = 'cn' | 'us' | 'hk'

export type MarketStatusCode =
  | 'open'
  | 'pre_market'
  | 'post_market'
  | 'closed'
  | 'closed_holiday'

export interface IndexQuote {
  market: MarketKind
  symbol: string
  name: string
  ts: string
  last_point: number
  prev_close: number
  change_point: number
  change_pct: number // 已是百分数(可负)
}

export interface MarketStatusInfo {
  market: MarketKind
  status: MarketStatusCode
  label: string
  is_trading_now: boolean
  as_of: string
  data_as_of: string | null
}

export interface MarketHomeOverview {
  market: MarketKind
  status: MarketStatusInfo
  indices: IndexQuote[]
}

export class MarketHomeApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`MarketHomeApi ${status}: ${detail}`)
    this.name = 'MarketHomeApiError'
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
    throw new MarketHomeApiError(r.status, detail)
  }
  return (await r.json()) as T
}

/** 市场首页总览(状态 + 大盘指数)· market = 'cn' | 'us'。 */
export function fetchMarketOverview(
  market: MarketKind,
  signal?: AbortSignal,
): Promise<MarketHomeOverview> {
  return getJson<MarketHomeOverview>(`/api/v1/${market}/overview`, signal)
}
