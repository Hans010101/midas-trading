/**
 * 加密永续合约虚拟交易 TanStack Query hooks · ADR-0019 v2 · M2-C.1。
 *
 * retry: 0(项目铁律 · 不分层叠加)。
 * 活仓 refetchInterval 8s(D9:浮盈/强平距离 5–10s 刷新)。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  type PerpFunding,
  type PerpOrder,
  type PerpPosition,
  type PlacePerpOrderInput,
  fetchPerpFunding,
  fetchPerpOrders,
  fetchPerpPositions,
  placePerpOrder,
} from '@/lib/api/perp'

export const PERP_KEY = {
  positions: (includeClosed?: boolean) =>
    ['perp', 'positions', includeClosed ?? false] as const,
  orders: (symbol?: string) => ['perp', 'orders', symbol ?? 'all'] as const,
  funding: (symbol?: string) => ['perp', 'funding', symbol ?? 'all'] as const,
}

function useToken(): { token: string; ready: boolean } {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function usePerpPositions(opts: { includeClosed?: boolean } = {}) {
  const { token, ready } = useToken()
  return useQuery<PerpPosition[]>({
    queryKey: PERP_KEY.positions(opts.includeClosed),
    queryFn: ({ signal }) => fetchPerpPositions(token, opts, signal),
    enabled: ready,
    retry: 0,
    refetchInterval: 8_000, // D9 · 浮盈 / 强平距离 ~8s 刷新
    staleTime: 6_000,
  })
}

export function usePerpOrders(opts: { symbol?: string; limit?: number } = {}) {
  const { token, ready } = useToken()
  return useQuery<PerpOrder[]>({
    queryKey: PERP_KEY.orders(opts.symbol),
    queryFn: ({ signal }) =>
      fetchPerpOrders(token, { symbol: opts.symbol, limit: opts.limit }, signal),
    enabled: ready,
    retry: 0,
    staleTime: 10_000,
  })
}

export function usePerpFunding(opts: { symbol?: string; limit?: number } = {}) {
  const { token, ready } = useToken()
  return useQuery<PerpFunding[]>({
    queryKey: PERP_KEY.funding(opts.symbol),
    queryFn: ({ signal }) =>
      fetchPerpFunding(token, { symbol: opts.symbol, limit: opts.limit }, signal),
    enabled: ready,
    retry: 0,
    staleTime: 30_000,
  })
}

export function usePlacePerpOrder() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<PerpOrder, Error, PlacePerpOrderInput>({
    mutationFn: (input) => placePerpOrder(token, input),
    onSuccess: () => {
      // 刷新 perp 持仓 / 流水 + 共用钱包(0008 account/portfolio)
      void queryClient.invalidateQueries({ queryKey: ['perp'] })
      void queryClient.invalidateQueries({ queryKey: ['virtual'] })
    },
  })
}
