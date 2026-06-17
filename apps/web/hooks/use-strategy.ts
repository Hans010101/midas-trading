/**
 * 策略信号 + 推荐 TanStack Query hooks · 形态A 单元3(ADR 0037 §5)。
 *
 * - retry: 0(项目铁律)· staleTime 60s · enabled 由调用方控制(策略开关关时不发请求)
 * - instrument + strategy 并入 queryKey,防 spot/perp、不同策略缓存串台。
 */

'use client'

import { useQuery } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  fetchStrategyRecommend,
  fetchStrategySignals,
  type Instrument,
  type StrategyKind,
  type StrategyRecommendResponse,
  type StrategySignalsResponse,
} from '@/lib/api/strategy'
import type { Market, Period } from '@midas/shared'

export interface UseStrategySignalsArgs {
  symbol: string
  market: Market
  period: Period
  strategy: StrategyKind
  instrument?: Instrument
  limit?: number
  enabled?: boolean
}

export function useStrategySignals(args: UseStrategySignalsArgs) {
  // ★ Pro 门控:带 session token 后端才识别 Pro · token 并入 queryKey(登录/登出即刷新锁态)
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useQuery<StrategySignalsResponse>({
    queryKey: [
      'strategy-signals', args.market, args.symbol, args.period,
      args.instrument ?? 'spot', args.strategy, args.limit ?? 300, token,
    ],
    queryFn: ({ signal }) =>
      fetchStrategySignals({
        symbol: args.symbol,
        market: args.market,
        period: args.period,
        strategy: args.strategy,
        instrument: args.instrument,
        limit: args.limit,
        token,
        signal,
      }),
    enabled: args.enabled ?? true,
    retry: 0,
    staleTime: 60_000,
  })
}

export interface UseStrategyRecommendArgs {
  symbol: string
  market: Market
  period: Period
  instrument?: Instrument
  limit?: number
  enabled?: boolean
}

export function useStrategyRecommend(args: UseStrategyRecommendArgs) {
  return useQuery<StrategyRecommendResponse>({
    queryKey: [
      'strategy-recommend', args.market, args.symbol, args.period,
      args.instrument ?? 'spot', args.limit ?? 300,
    ],
    queryFn: ({ signal }) =>
      fetchStrategyRecommend({
        symbol: args.symbol,
        market: args.market,
        period: args.period,
        instrument: args.instrument,
        limit: args.limit,
        signal,
      }),
    enabled: args.enabled ?? true,
    retry: 0,
    staleTime: 60_000,
  })
}
