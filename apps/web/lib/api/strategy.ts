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

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export type StrategyKind =
  | 'ma_cross'
  | 'rsi_reversal'
  | 'boll_reversion'
  | 'macd_cross'
  | 'kdj_cross'
  // 第二刀:极端信号(★仅 crypto perp · 合约 funding/OI/多空比情绪 · 现货不出)
  | 'extreme'
export type SignalKind = 'buy' | 'sell'
export type Instrument = 'spot' | 'perp'

export interface StrategySignal {
  ts: string
  price: number
  kind: SignalKind
  reason: string
  /** ⑤ 关键价位(形态A 批2 · 策略相关)· ma_cross {MA5,MA20} · rsi {RSI,超卖线} · boll {上轨,中轨,下轨} */
  levels: Record<string, number>
  /** ⑥ 成色数值(形态A 批2 · 只 rsi/boll · ma_cross 为 null)· 越大越强 */
  strength: number | null
  /** ⑥ 成色可读(如「超卖深度 · RSI 探至 18」「偏离下轨 10.7%」)· ma_cross 为 null */
  strength_note: string | null
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
  // ★ Pro 门控:true = 非 Pro(未登录/免费)· 此时 signals 为空(后端无真实信号)
  locked: boolean
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

async function _getJson<T>(
  url: string, signal?: AbortSignal, token?: string,
): Promise<T> {
  const r = await fetch(url, {
    signal,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })
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
  /** ★ Pro 门控:登录态 session token · 带上后端才识别 Pro(无 token = 未登录 = locked)。 */
  token?: string
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
    args.token,
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
