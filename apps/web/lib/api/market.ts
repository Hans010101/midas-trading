/**
 * 点金 Midas · 市场数据 API client。
 *
 * 包装 /api/v1/market/kline 和 /api/v1/market/symbols 两个端点,
 * 处理错误码 (404 / 503 / 502 / 等) 让 useKline hook 能区分:
 *   - 404 → reason='not-found'(标的不存在)
 *   - 503 → reason='unavailable'(上游不可达)
 *   - 200 但 items=[] → reason='empty'(回填中)
 */

import type { KlineResponse, Market, Period, SymbolMeta } from '@midas/shared'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type MarketApiErrorKind = 'not-found' | 'unavailable' | 'bad-gateway' | 'unknown'

export class MarketApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly kind: MarketApiErrorKind,
  ) {
    super(`MarketApi ${status} (${kind}): ${detail}`)
    this.name = 'MarketApiError'
  }
}

function kindFromStatus(status: number): MarketApiErrorKind {
  if (status === 404) return 'not-found'
  if (status === 503) return 'unavailable'
  if (status === 502) return 'bad-gateway'
  return 'unknown'
}

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${resp.status}`
  } catch {
    return `HTTP ${resp.status}`
  }
}

export interface FetchKlineOptions {
  symbol: string
  market: Market
  period: Period
  limit?: number
  signal?: AbortSignal
}

export async function fetchKline(opts: FetchKlineOptions): Promise<KlineResponse> {
  const params = new URLSearchParams({
    symbol: opts.symbol,
    market: opts.market,
    period: opts.period,
    limit: String(opts.limit ?? 500),
  })
  const r = await fetch(`${API_BASE}/api/v1/market/kline?${params.toString()}`, {
    signal: opts.signal,
  })
  if (!r.ok) {
    throw new MarketApiError(r.status, await readDetail(r), kindFromStatus(r.status))
  }
  return (await r.json()) as KlineResponse
}

export interface SearchSymbolsOptions {
  q: string
  market?: Market
  limit?: number
  signal?: AbortSignal
}

export async function searchSymbols(opts: SearchSymbolsOptions): Promise<SymbolMeta[]> {
  const params = new URLSearchParams({ q: opts.q })
  if (opts.market) params.set('market', opts.market)
  if (opts.limit !== undefined) params.set('limit', String(opts.limit))
  const r = await fetch(`${API_BASE}/api/v1/market/symbols?${params.toString()}`, {
    signal: opts.signal,
  })
  if (!r.ok) {
    throw new MarketApiError(r.status, await readDetail(r), kindFromStatus(r.status))
  }
  return (await r.json()) as SymbolMeta[]
}
