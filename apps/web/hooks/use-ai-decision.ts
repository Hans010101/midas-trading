/**
 * AI 决策卡 TanStack Query hook · 0012 ADR M1 二波 Checkpoint Z。
 *
 * - retry: 0(项目铁律 · transport 层已在 LiteLLM/backend retry)
 * - staleTime 5min(应用层 Redis cache 4h · 前端短 staleTime 让用户切回来不会等)
 * - enabled 由调用方控制(用户切到「我的账户」时可关掉)
 */

'use client'

import { useQuery } from '@tanstack/react-query'
import { useLocale } from 'next-intl'
import { useSession } from 'next-auth/react'

import {
  fetchDecisionCard, type DecisionCard,
} from '@/lib/api/ai-decision'
import type { Market, Period } from '@midas/shared'

export interface UseAiDecisionArgs {
  symbol: string
  market: Market
  period: Period
  limit?: number
  /** 'spot'(默认)· 'perp' 合约。并入 queryKey 防 spot/perp 缓存串台。 */
  instrument?: 'spot' | 'perp'
  enabled?: boolean
}

export function useAiDecision(args: UseAiDecisionArgs) {
  const locale = useLocale()
  // 会话恢复完成后再请求，避免已登录用户进页时先收到未登录锁态。
  const { data: session, status } = useSession()
  const token = session?.accessToken ?? ''
  return useQuery<DecisionCard>({
    queryKey: [
      'ai-decision', args.market, args.symbol, args.period, args.limit ?? 300,
      args.instrument ?? 'spot', locale, token,
    ],
    queryFn: ({ signal }) =>
      fetchDecisionCard({
        symbol: args.symbol,
        market: args.market,
        period: args.period,
        limit: args.limit,
        instrument: args.instrument,
        locale,
        token,
        signal,
      }),
    enabled: (args.enabled ?? true) && status !== 'loading',
    retry: 0,
    staleTime: 5 * 60_000,
  })
}
