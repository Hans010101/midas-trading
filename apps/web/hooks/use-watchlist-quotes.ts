/**
 * 自选股静态报价拉取(0007 § 5)。
 *
 * 每个 item 单独发一次 /api/v1/market/kline?limit=2 拿到最后两根 K,
 * 算出 close + prev_close + 涨跌幅。
 *
 * 30s 轮询 + 25s staleTime 防 re-render 重复请求(0007 决策点 ③ 加固)。
 * retry: 0(遵守项目铁律 · retry 只在最贴 transport 的一层做)。
 */

'use client'

import { useQueries } from '@tanstack/react-query'

import { fetchKline } from '@/lib/api/market'
import type { WatchlistItem } from '@/lib/api/watchlist'

export interface Quote {
  symbol: string
  close: number | null
  change: number | null
  changePct: number | null
  isLoading: boolean
  isError: boolean
}

export function useWatchlistQuotes(items: WatchlistItem[]): Quote[] {
  const queries = useQueries({
    queries: items.map((it) => ({
      queryKey: ['quote', it.market, it.symbol] as const,
      queryFn: async ({ signal }: { signal?: AbortSignal }) => {
        const resp = await fetchKline({
          symbol: it.symbol,
          market: it.market,
          period: '1d',
          limit: 2,
          signal,
        })
        return resp.items
      },
      refetchInterval: 30_000,
      staleTime: 25_000,
      retry: 0,
    })),
  })

  return items.map((it, idx) => {
    const q = queries[idx]
    const klines = q?.data ?? []
    const last = klines[klines.length - 1]
    const prev = klines[klines.length - 2]
    const close = last?.close ?? null
    const prevClose = prev?.close ?? null
    const change = close !== null && prevClose !== null ? close - prevClose : null
    const changePct =
      change !== null && prevClose !== null && prevClose !== 0
        ? (change / prevClose) * 100
        : null
    return {
      symbol: it.symbol,
      close,
      change,
      changePct,
      isLoading: q?.isLoading ?? false,
      isError: q?.isError ?? false,
    }
  })
}
