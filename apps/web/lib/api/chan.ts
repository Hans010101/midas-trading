/**
 * 缠论分析 API client · 0011 ADR § 5。
 *
 * GET /api/v1/analysis/chan?symbol=&market=&period=&limit=
 * 返回笔(BI)/ 顶底分型(FX)/ 中枢(简化版)。
 * 段 / 买卖点 / 多周期联动 由 M1 第二波 AI 决策卡扩展。
 */

import type { Market, Period } from '@midas/shared'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface FractalPoint {
  ts: string
  price: number
  kind: 'G' | 'D'  // G=顶分型 D=底分型
}

export interface Bi {
  start_ts: string
  end_ts: string
  start_price: number
  end_price: number
  direction: 'up' | 'down'
  high: number
  low: number
  power: number
  length: number
}

export interface Zhongshu {
  start_ts: string
  end_ts: string
  high: number
  low: number
}

export type BuySellPointKind = 'B1' | 'B2' | 'B3' | 'S1' | 'S2' | 'S3'

export interface BuySellPoint {
  ts: string
  price: number
  kind: BuySellPointKind
  description: string
}

export interface ChanAnalysis {
  symbol: string
  market: Market
  period: Period
  bar_count: number
  fractals: FractalPoint[]
  bis: Bi[]
  zhongshus: Zhongshu[]
  buy_sell_points: BuySellPoint[]   // M1 第二波 · czsc 6 类买卖点
  disclaimer: string
}

export class ChanApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`ChanApi ${status}: ${detail}`)
    this.name = 'ChanApiError'
  }
}

export interface FetchChanArgs {
  symbol: string
  market: Market
  period: Period
  limit?: number
  signal?: AbortSignal
}

export async function fetchChanAnalysis(args: FetchChanArgs): Promise<ChanAnalysis> {
  const params = new URLSearchParams({
    symbol: args.symbol,
    market: args.market,
    period: args.period,
    limit: String(args.limit ?? 300),
  })
  const r = await fetch(
    `${API_BASE}/api/v1/analysis/chan?${params.toString()}`,
    { signal: args.signal },
  )
  if (!r.ok) {
    let detail = `HTTP ${r.status}`
    try {
      const body = (await r.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* ignore */
    }
    throw new ChanApiError(r.status, detail)
  }
  return (await r.json()) as ChanAnalysis
}
