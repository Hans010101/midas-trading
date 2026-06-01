/**
 * 策略信号 + 推荐 API client · 形态A 单元3(ADR 0037 §5.1)。
 *
 * GET /api/v1/analysis/strategy-signals   → 某标的某策略的历史买卖信号点序列 + 当前是否触发
 * GET /api/v1/analysis/strategy-recommend → 推荐该标的现在适合哪个策略 + 理由
 *
 * 🔴 红线:纯展示型只读数据 · 信号只画在 K 线上,不下单 / 不自动交易;
 * 用户看完信号要下单走第一层「一键模拟下单」。
 */

import type { Market, Period } from '@midas/shared'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type StrategyKind = 'ma_cross' | 'rsi_reversal' | 'boll_reversion'
export type SignalKind = 'buy' | 'sell'
export type Instrument = 'spot' | 'perp'

export interface StrategySignal {
  ts: string
  price: number
  kind: SignalKind
  reason: string
}

export interface StrategySignalsResponse {
  symbol: string
  market: Market
  period: Period
  instrument: Instrument
  strategy: StrategyKind
  bar_count: number
  signals: StrategySignal[]
  current_triggered: boolean
  last_signal: StrategySignal | null
}

export interface StrategyRecommendResponse {
  symbol: string
  market: Market
  period: Period
  instrument: Instrument
  recommended_strategy: StrategyKind
  reason: string
}

export class StrategyApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`StrategyApi ${status}: ${detail}`)
    this.name = 'StrategyApiError'
  }
}

async function _getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal })
  if (!r.ok) {
    let detail = `HTTP ${r.status}`
    try {
      const body = (await r.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* ignore */
    }
    throw new StrategyApiError(r.status, detail)
  }
  return (await r.json()) as T
}

export interface FetchStrategySignalsArgs {
  symbol: string
  market: Market
  period: Period
  strategy: StrategyKind
  limit?: number
  instrument?: Instrument
  signal?: AbortSignal
}

export async function fetchStrategySignals(
  args: FetchStrategySignalsArgs,
): Promise<StrategySignalsResponse> {
  const params = new URLSearchParams({
    symbol: args.symbol,
    market: args.market,
    period: args.period,
    strategy: args.strategy,
    limit: String(args.limit ?? 300),
  })
  if (args.instrument) params.set('instrument', args.instrument)
  return _getJson<StrategySignalsResponse>(
    `${API_BASE}/api/v1/analysis/strategy-signals?${params.toString()}`,
    args.signal,
  )
}

export interface FetchStrategyRecommendArgs {
  symbol: string
  market: Market
  period: Period
  limit?: number
  instrument?: Instrument
  signal?: AbortSignal
}

export async function fetchStrategyRecommend(
  args: FetchStrategyRecommendArgs,
): Promise<StrategyRecommendResponse> {
  const params = new URLSearchParams({
    symbol: args.symbol,
    market: args.market,
    period: args.period,
    limit: String(args.limit ?? 300),
  })
  if (args.instrument) params.set('instrument', args.instrument)
  return _getJson<StrategyRecommendResponse>(
    `${API_BASE}/api/v1/analysis/strategy-recommend?${params.toString()}`,
    args.signal,
  )
}
