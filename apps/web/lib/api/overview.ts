/**
 * 全球指标概览 API client(ADR 0035 阶段 A)。
 *
 * 只读端点:GET /api/v1/overview/global · 按分类(环球指数/商品/外汇/债券/加密)分组。
 * 红线:纯展示 · market 是地区码非交易市场 · 接不上交给页面显示空态,绝不伪造数据。
 */

import type { QuoteUnit } from '@/components/market-home/index-card'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface OverviewQuote {
  market: string // 地区码(us/jp/hk/global/fx/crypto)· 非交易市场
  symbol: string
  name: string
  category: string
  unit: QuoteUnit
  ts: string
  last_point: number
  prev_close: number
  change_point: number
  change_pct: number
}

export interface OverviewGroup {
  category: string
  label: string
  items: OverviewQuote[]
}

export interface GlobalOverviewResponse {
  groups: OverviewGroup[]
  as_of: string
}

export class OverviewApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`OverviewApi ${status}: ${detail}`)
    this.name = 'OverviewApiError'
  }
}

export function fetchGlobalOverview(signal?: AbortSignal): Promise<GlobalOverviewResponse> {
  return getJson<GlobalOverviewResponse>('/api/v1/overview/global', signal)
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
    throw new OverviewApiError(r.status, detail)
  }
  return (await r.json()) as T
}
