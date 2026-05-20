/**
 * /api/v1/market/symbols 搜索包装(给 Cmd+K 用)。
 *
 * - 输入 ≥ 1 字符才发请求
 * - staleTime 60s(同样的关键词短时间内复用结果)
 * - retry: 0(项目铁律)
 */

'use client'

import { useQuery } from '@tanstack/react-query'

import { searchSymbols } from '@/lib/api/market'
import type { Market } from '@midas/shared'

export function useSymbolSearch(query: string, market?: Market) {
  const trimmed = query.trim()
  return useQuery({
    queryKey: ['symbols', market ?? 'all', trimmed],
    queryFn: ({ signal }) =>
      searchSymbols({ q: trimmed, market, limit: 30, signal }),
    enabled: trimmed.length >= 1,
    staleTime: 60_000,
    retry: 0,
  })
}
