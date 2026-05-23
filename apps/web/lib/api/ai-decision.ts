/**
 * AI 决策卡 API client · 0012 ADR M1 二波 Checkpoint Z。
 *
 * GET /api/v1/analysis/decision-card?symbol=&market=&period=&limit=
 * 返回 DecisionCardResponse(综合评分 + 技术面 Agent + 缠论买卖点 + disclaimer)。
 *
 * mock 边界:后端 DEEPSEEK_API_KEY 未配置时,llm_mode='mock' · 返回固定假数据 ·
 * 前端 UI 不区分 mock / real(都正常渲染)· 仅 footer 显示 mock 标识(便于调试)。
 */

import type { Market, Period } from '@midas/shared'

import type { BuySellPoint, BuySellPointKind } from '@/lib/api/chan'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type AgentName =
  | 'technical' | 'fundamental' | 'news' | 'value'
  | 'onchain' | 'derivatives' | 'sentiment'

export interface AgentScore {
  name: AgentName
  score: number               // -100..100
  confidence: number          // 0..1
  rationale: string
  key_levels: number[]
}

export type CompositeLabel = '强多' | '弱多' | '中性' | '弱空' | '强空'

export interface DecisionCard {
  symbol: string
  market: Market
  period: Period
  generated_at: string

  composite_score: number
  composite_label: CompositeLabel
  composite_confidence: number

  agent_scores: AgentScore[]
  contradiction: string | null

  narrative: string
  chan_signals: BuySellPoint[]

  disclaimer: string
  cached: boolean
  token_usage: number
  llm_mode: 'mock' | 'real'
}

export class AiDecisionApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`AiDecisionApi ${status}: ${detail}`)
    this.name = 'AiDecisionApiError'
  }
}

export interface FetchDecisionCardArgs {
  symbol: string
  market: Market
  period: Period
  limit?: number
  /** 'spot'(默认)· 'perp' USDT-M 永续合约 · 只 crypto 支持。不传 → 后端默认 spot。 */
  instrument?: 'spot' | 'perp'
  signal?: AbortSignal
}

export async function fetchDecisionCard(
  args: FetchDecisionCardArgs,
): Promise<DecisionCard> {
  const params = new URLSearchParams({
    symbol: args.symbol,
    market: args.market,
    period: args.period,
    limit: String(args.limit ?? 300),
  })
  if (args.instrument) params.set('instrument', args.instrument)
  const r = await fetch(
    `${API_BASE}/api/v1/analysis/decision-card?${params.toString()}`,
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
    throw new AiDecisionApiError(r.status, detail)
  }
  return (await r.json()) as DecisionCard
}

// 工具函数 · 给 chan-overlay / decision-card 共用
export function buySellKindIsBuy(kind: BuySellPointKind): boolean {
  return kind.startsWith('B')
}
