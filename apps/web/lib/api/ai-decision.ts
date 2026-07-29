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
import { withLang } from '@/lib/i18n/lang-headers'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

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

// 可下单建议(0036 批次甲)· 镜像后端 ActionableAdvice
export type ActionableDirection =
  | 'buy' | 'sell' | 'hold' | 'open_long' | 'open_short' | 'close'

export interface ActionableAdvice {
  direction: ActionableDirection
  actionable: boolean        // direction !== hold(前端是否出「一键模拟下单」)
  basis: string              // 模板化依据
  size_note: string          // 仓位口径(固定下单预设)
  hint: string               // 操作提示(模拟语境)
  disclaimer: string
}

// 交易计划参考(三价位后端规则算 + AI plan_note)· 镜像后端 TradingPlan
export type PlanDirection = 'long' | 'short' | 'neutral'

export interface TradingPlan {
  direction: PlanDirection
  entry_low: number | null
  entry_high: number | null
  stop: number | null
  target1: number | null
  target2: number | null
  risk_reward: number | null
  plan_note: string
}

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

  // 可下单建议(0036 批次甲)· 后端 actionable 适配层派生 · null 表示无(老缓存/中性)
  actionable: ActionableAdvice | null

  // 交易计划参考 · 后端规则算 · null 表示无(老缓存 / 中性 / 非 Pro 空壳)
  trading_plan: TradingPlan | null

  // ★事件日程层 P0:近期重大事件风险提示(后端纯模板·只提示波动不给方向·尾带免责)·
  //   可选:老缓存/旧后端无此字段 · null/undefined = 无事件不渲染
  event_risk?: string | null

  disclaimer: string
  cached: boolean
  token_usage: number
  llm_mode: 'mock' | 'real'

  // ★ Pro 门控:true = 非 Pro(未登录/免费)· 此时上方决策字段全为空壳(后端无真实内容)
  locked: boolean
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
  /** 与 X-Lang 同步写入 URL，隔离浏览器的语言响应缓存。 */
  locale?: string
  /** ★ Pro 门控:登录态 session token · 带上后端才识别 Pro(无 token = 未登录 = locked)。 */
  token?: string
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
  if (args.locale) params.set('lang', args.locale)
  const r = await fetch(
    `${API_BASE}/api/v1/analysis/decision-card?${params.toString()}`,
    {
      signal: args.signal,
      // ★X-Lang(cookie locale)→ 后端 resolve_lang 出对应语言的 AI 分析/免责。
      //   guest 靠它、登录用户切换即时生效(server 侧另有 language_pref 扩回兜底)。
      headers: withLang(args.token ? { Authorization: `Bearer ${args.token}` } : undefined),
    },
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
