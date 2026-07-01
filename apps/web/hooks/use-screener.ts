/**
 * 选股筛选器 hook · 股票第一批 功能1 · 1a · retry 0(项目铁律)。
 */

'use client'

import { useMutation } from '@tanstack/react-query'

import {
  type ScreenerFilters,
  type ScreenerResponse,
  type StockMarket,
  runScreener,
} from '@/lib/api/screener'

export function useScreener() {
  return useMutation<
    ScreenerResponse,
    Error,
    { market: StockMarket; filters: ScreenerFilters; page?: number }
  >({
    mutationFn: ({ market, filters, page }) => runScreener(market, filters, page ?? 1),
    retry: 0,
  })
}
