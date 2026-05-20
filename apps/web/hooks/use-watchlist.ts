/**
 * TanStack Query 包装 watchlist 4 端点。
 *
 * - useWatchlist: GET 列表(JWT 来自 useSession)
 * - useAddToWatchlist: POST,加完 invalidate
 * - useDeleteFromWatchlist: DELETE,删完 invalidate
 * - useReorderWatchlist: PUT reorder,改完 invalidate
 *
 * retry: 0(遵守项目铁律 · retry 只在最贴 transport 的一层做)
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  addToWatchlist,
  deleteFromWatchlist,
  fetchWatchlist,
  reorderWatchlist,
  type WatchlistItem,
} from '@/lib/api/watchlist'
import type { Market } from '@midas/shared'

export const WATCHLIST_QUERY_KEY = ['watchlist'] as const

export function useWatchlist() {
  const { data: session, status } = useSession()
  const token = session?.accessToken ?? ''
  return useQuery({
    queryKey: WATCHLIST_QUERY_KEY,
    queryFn: ({ signal }) => fetchWatchlist(token, signal),
    enabled: status === 'authenticated' && token.length > 0,
    retry: 0,
    staleTime: 10_000,
  })
}

export function useAddToWatchlist() {
  const queryClient = useQueryClient()
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useMutation({
    mutationFn: async (vars: { symbol: string; market: Market }) =>
      addToWatchlist(token, vars.symbol, vars.market),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: WATCHLIST_QUERY_KEY })
    },
  })
}

export function useDeleteFromWatchlist() {
  const queryClient = useQueryClient()
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useMutation({
    mutationFn: async (id: number) => deleteFromWatchlist(token, id),
    // 乐观更新:删之前先从缓存里移除,API 失败时回滚
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: WATCHLIST_QUERY_KEY })
      const prev = queryClient.getQueryData<WatchlistItem[]>(WATCHLIST_QUERY_KEY)
      queryClient.setQueryData<WatchlistItem[]>(WATCHLIST_QUERY_KEY, (old) =>
        (old ?? []).filter((it) => it.id !== id),
      )
      return { prev }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(WATCHLIST_QUERY_KEY, ctx.prev)
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: WATCHLIST_QUERY_KEY })
    },
  })
}

export function useReorderWatchlist() {
  const queryClient = useQueryClient()
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useMutation({
    mutationFn: async (itemIds: number[]) => reorderWatchlist(token, itemIds),
    // 乐观更新:reorder 之前先把缓存里的顺序改了,失败回滚
    onMutate: async (itemIds) => {
      await queryClient.cancelQueries({ queryKey: WATCHLIST_QUERY_KEY })
      const prev = queryClient.getQueryData<WatchlistItem[]>(WATCHLIST_QUERY_KEY)
      if (prev) {
        const byId = new Map(prev.map((it) => [it.id, it]))
        const reordered: WatchlistItem[] = []
        itemIds.forEach((id, idx) => {
          const it = byId.get(id)
          if (it) reordered.push({ ...it, sort_order: idx })
        })
        // 把没出现在 itemIds 里的(理论不会发生)追加在末尾
        for (const it of prev) {
          if (!itemIds.includes(it.id)) reordered.push(it)
        }
        queryClient.setQueryData<WatchlistItem[]>(WATCHLIST_QUERY_KEY, reordered)
      }
      return { prev }
    },
    onError: (_err, _ids, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(WATCHLIST_QUERY_KEY, ctx.prev)
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: WATCHLIST_QUERY_KEY })
    },
  })
}
