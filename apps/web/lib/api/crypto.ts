/**
 * Crypto Pro · 合约维度数据 API client(M2-D 接真实数据)。
 *
 * 包装 /api/v1/crypto/* 端点(后端 0017 ADR · M2-A 已实装 ClickHouse 读):
 *   GET /futures/{symbol}/open-interest     · OI 时间序列
 *   GET /futures/{symbol}/long-short-ratio  · 三套多空比(账户/持仓/taker)
 *   GET /futures/{symbol}/funding-rate      · 资金费率时间序列
 *   GET /futures/{symbol}/info              · 合约元信息(标记价/下次费率)
 *
 * symbol 用 Binance Futures 风格 `BTCUSDT`(无斜杠)· 跟现货 kline 的
 * ccxt 风格 `BTC/USDT` 不同 · 调用方负责转换。
 *
 * 原则:上游未提供的维度不编造，由前端隐藏对应空卡片。
 */

import { fetchWithRetry } from './fetch-with-retry'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export class CryptoApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`CryptoApi ${status}: ${detail}`)
    this.name = 'CryptoApiError'
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
    throw new CryptoApiError(r.status, detail)
  }
  return (await r.json()) as T
}

// ── 类型 · 跟后端 schemas/crypto.py 严格对齐 ──────────────────────────────

export interface OpenInterestPoint {
  symbol: string
  ts: string
  oi_coin: number
  oi_usd: number
}
export interface OpenInterestResponse {
  symbol: string
  items: OpenInterestPoint[]
  source?: string
}

export interface LongShortPoint {
  symbol: string
  ts: string
  top_account_long: number
  top_account_short: number
  top_account_ratio: number
  top_position_long: number
  top_position_short: number
  top_position_ratio: number
  taker_buy_vol: number
  taker_sell_vol: number
  taker_ratio: number
  // 刀C · 全市场人数比(globalLongShortAccountRatio)· 0 = 该行未采(老行哨兵 · 前端过滤)
  global_account_long: number
  global_account_short: number
  global_account_ratio: number
}
export interface LongShortRatioResponse {
  symbol: string
  items: LongShortPoint[]
  source?: string
  unavailable_fields?: string[]
}

export interface FundingRatePoint {
  symbol: string
  ts: string
  rate: number
  mark_price: number
}
export interface FundingRateResponse {
  symbol: string
  items: FundingRatePoint[]
  source?: string
}

export interface FuturesSymbolInfo {
  symbol: string
  base_asset: string
  quote_asset: string
  contract_type: 'perpetual' | 'current_quarter' | 'next_quarter'
  mark_price: number
  index_price: number
  last_funding_rate: number
  next_funding_time: string
  max_leverage: number
  open_interest_coin: number
  open_interest_usd: number
}

// ── fetch 函数 ────────────────────────────────────────────────────────────

export function fetchOpenInterest(
  symbol: string,
  limit = 96,
  signal?: AbortSignal,
): Promise<OpenInterestResponse> {
  return getJson<OpenInterestResponse>(
    `/api/v1/crypto/futures/${symbol}/open-interest?limit=${limit}`,
    signal,
  )
}

export function fetchLongShortRatio(
  symbol: string,
  limit = 96,
  signal?: AbortSignal,
): Promise<LongShortRatioResponse> {
  return getJson<LongShortRatioResponse>(
    `/api/v1/crypto/futures/${symbol}/long-short-ratio?limit=${limit}`,
    signal,
  )
}

export function fetchFundingRate(
  symbol: string,
  limit = 100,
  signal?: AbortSignal,
): Promise<FundingRateResponse> {
  return getJson<FundingRateResponse>(
    `/api/v1/crypto/futures/${symbol}/funding-rate?limit=${limit}`,
    signal,
  )
}

export function fetchFuturesInfo(
  symbol: string,
  signal?: AbortSignal,
): Promise<FuturesSymbolInfo> {
  return getJson<FuturesSymbolInfo>(
    `/api/v1/crypto/futures/${symbol}/info`,
    signal,
  )
}

// ── 基差时序(详情页 ⑥ 基差图)· M2-C.2.4 ───────────────────────────────────
export interface BasisPoint {
  ts: string
  mark_price: number
  index_price: number
  basis_pct: number // (mark − index) / index × 100 · 可负
}
export interface BasisSeriesResponse {
  symbol: string
  items: BasisPoint[]
  source?: string
}

export function fetchBasisSeries(
  symbol: string,
  limit = 288,
  signal?: AbortSignal,
): Promise<BasisSeriesResponse> {
  return getJson<BasisSeriesResponse>(
    `/api/v1/crypto/futures/${symbol}/basis?limit=${limit}`,
    signal,
  )
}
