/**
 * AI 决策卡 TanStack Query hook · 0012 ADR M1 二波 Checkpoint Z。
 *
 * - retry: 0(项目铁律 · transport 层已在 LiteLLM/backend retry)
 * - staleTime 5min(应用层 Redis cache 4h · 前端短 staleTime 让用户切回来不会等)
 * - enabled 由调用方控制(用户切到「我的账户」时可关掉)
 */

'use client'

import { useQuery } from '@tanstack/react-query'

import {
  fetchDecisionCard, type DecisionCard,
} from '@/lib/api/ai-decision'
import type { Market, Period } from '@midas/shared'

export interface UseAiDecisionArgs {
  symbol: string
  market: Market
  period: Period
  limit?: number
  enabled?: boolean
}

export function useAiDecision(args: UseAiDecisionArgs) {
  return useQuery<DecisionCard>({
    queryKey: [
      'ai-decision', args.market, args.symbol, args.period, args.limit ?? 300,
    ],
    queryFn: ({ signal }) =>
      fetchDecisionCard({
        symbol: args.symbol,
        market: args.market,
        period: args.period,
        limit: args.limit,
        signal,
      }),
    enabled: args.enabled ?? true,
    retry: 0,
    staleTime: 5 * 60_000,
  })
}
