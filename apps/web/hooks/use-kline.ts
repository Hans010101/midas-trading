'use client'

/**
 * useKline:TanStack Query v5 包装 /api/v1/market/kline。
 *
 * 缓存策略:
 *   - queryKey 含 symbol/market/period/limit,粒度足够区分所有调用
 *   - staleTime 60s(K 线数据不会秒级变化,1 分钟内复用缓存)
 *   - 不自动 refetchOnWindowFocus(用户切到别的 tab 回来时别打扰)
 *
 * EmptyKline 的三态判断由调用方做(基于 query.status / data.items.length /
 * (error as MarketApiError).kind)。
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import type { KlineResponse, Market, Period } from '@midas/shared'

import { fetchKline } from '@/lib/api/market'

export interface UseKlineArgs {
  symbol: string
  market: Market
  period: Period
  limit?: number
  /** 'spot'(默认)· 'perp' 合约。务必并入 queryKey,否则 spot/perp 同 symbol 缓存串台。 */
  instrument?: 'spot' | 'perp'
  enabled?: boolean
}

export function useKline(args: UseKlineArgs): UseQueryResult<KlineResponse> {
  return useQuery({
    queryKey: [
      'kline', args.market, args.symbol, args.period, args.limit ?? 500,
      args.instrument ?? 'spot',
    ],
    queryFn: ({ signal }) =>
      fetchKline({
        symbol: args.symbol,
        market: args.market,
        period: args.period,
        limit: args.limit,
        instrument: args.instrument,
        signal,
      }),
    staleTime: 60 * 1000,
    // 后端 BaseDataSource._retry 已经做 4 次重试(1/5/15s 退避,~22s 才确定失败),
    // 前端再 retry 会把 503 失败时长拉到 44s+,体验崩。后端失败 = 前端立刻 EmptyKline。
    retry: 0,
    enabled: args.enabled ?? true,
  })
}
