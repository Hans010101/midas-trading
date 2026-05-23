/**
 * 缠论分析 TanStack Query hook · 0011 ADR。
 *
 * - retry: 0(项目铁律)
 * - staleTime 60s(K 线粒度内复用)
 * - enabled 由调用方控制(缠论开关关时不发请求)
 */

'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchChanAnalysis, type ChanAnalysis } from '@/lib/api/chan'
import type { Market, Period } from '@midas/shared'

export interface UseChanArgs {
  symbol: string
  market: Market
  period: Period
  limit?: number
  /** 'spot'(默认)· 'perp' 合约。并入 queryKey 防 spot/perp 缓存串台。 */
  instrument?: 'spot' | 'perp'
  enabled?: boolean
}

export function useChan(args: UseChanArgs) {
  return useQuery<ChanAnalysis>({
    queryKey: [
      'chan', args.market, args.symbol, args.period, args.limit ?? 300,
      args.instrument ?? 'spot',
    ],
    queryFn: ({ signal }) =>
      fetchChanAnalysis({
        symbol: args.symbol,
        market: args.market,
        period: args.period,
        limit: args.limit,
        instrument: args.instrument,
        signal,
      }),
    enabled: args.enabled ?? true,
    retry: 0,
    staleTime: 60_000,
  })
}
