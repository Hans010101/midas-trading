/**
 * 虚拟交易 TanStack Query hooks · 0008 v2。
 *
 * retry: 0(项目铁律 · retry 不分层叠加)。
 * portfolio refetchInterval 30s + staleTime 25s(跟 watchlist 同源策略)。
 */

'use client'

import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  type AccountSummary,
  type AiOrderInput,
  type AiOrderResult,
  type EquityCurves,
  type Position,
  type PlaceOrderInput,
  type VirtualAccount,
  type VirtualOrder,
  activateOrResetAccount,
  fetchAccount,
  fetchAccounts,
  fetchEquityCurves,
  fetchHkBoardLot,
  fetchOrders,
  fetchPortfolio,
  fetchPositions,
  placeAiOrder,
  placeOrder,
} from '@/lib/api/virtual'
import type { Market } from '@midas/shared'

export const VIRTUAL_KEY = {
  accounts: ['virtual', 'accounts'] as const,
  account: (m: Market) => ['virtual', 'accounts', m] as const,
  portfolio: ['virtual', 'portfolio'] as const,
  orders: (m?: Market) => ['virtual', 'orders', m ?? 'all'] as const,
  positions: (m?: Market, includeClosed?: boolean) =>
    ['virtual', 'positions', m ?? 'all', includeClosed ?? false] as const,
  equityCurves: (days: number) => ['virtual', 'equity-curves', days] as const,
  hkBoardLot: (symbol: string) => ['virtual', 'hk-board-lot', symbol] as const,
}

function useToken(): { token: string; ready: boolean } {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function useAccounts() {
  const { token, ready } = useToken()
  return useQuery<VirtualAccount[]>({
    queryKey: VIRTUAL_KEY.accounts,
    queryFn: ({ signal }) => fetchAccounts(token, signal),
    enabled: ready,
    retry: 0,
    staleTime: 10_000,
  })
}

export function useAccount(market: Market) {
  const { token, ready } = useToken()
  return useQuery<VirtualAccount | null>({
    queryKey: VIRTUAL_KEY.account(market),
    queryFn: ({ signal }) => fetchAccount(token, market, signal),
    enabled: ready,
    retry: 0,
    staleTime: 10_000,
  })
}

// 港股每手股数 · 只读公开配置(无需 token)· 仅 hk 下单面用 · lot 极少变 → 长缓存
export function useHkBoardLot(symbol: string, enabled = true) {
  return useQuery<number | null>({
    queryKey: VIRTUAL_KEY.hkBoardLot(symbol),
    queryFn: ({ signal }) => fetchHkBoardLot(symbol, signal),
    enabled: enabled && symbol.length > 0,
    retry: 0,
    staleTime: 60 * 60_000,
  })
}

export function useActivateAccount() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation({
    mutationFn: (vars: { market: Market; initialCapital: string }) =>
      activateOrResetAccount(token, vars.market, vars.initialCapital),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['virtual'] })
    },
  })
}

export function usePortfolio() {
  const { token, ready } = useToken()
  return useQuery<AccountSummary[]>({
    queryKey: VIRTUAL_KEY.portfolio,
    queryFn: ({ signal }) => fetchPortfolio(token, signal),
    enabled: ready,
    retry: 0,
    refetchInterval: 30_000,
    staleTime: 25_000,
  })
}

export function usePlaceOrder() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<VirtualOrder, Error, PlaceOrderInput>({
    mutationFn: (input) => placeOrder(token, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['virtual'] })
    },
  })
}

// AI 一键模拟下单(0036 批次甲)· 走 ai-order 端点(source=ai_signal · 同一虚拟撮合引擎)
// 成交后刷新 virtual 查询(持仓 / 账户 / 流水),与手动下单一致。
export function useAiOrder() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<AiOrderResult, Error, AiOrderInput>({
    mutationFn: (input) => placeAiOrder(token, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['virtual'] })
    },
  })
}

export function useOrders(opts: {
  market?: Market
  limit?: number
} = {}) {
  const { token, ready } = useToken()
  return useQuery<VirtualOrder[]>({
    queryKey: VIRTUAL_KEY.orders(opts.market),
    queryFn: ({ signal }) =>
      fetchOrders(token, { market: opts.market, limit: opts.limit }, signal),
    enabled: ready,
    retry: 0,
    staleTime: 10_000,
  })
}

export function usePositions(opts: {
  market?: Market
  includeClosed?: boolean
} = {}) {
  const { token, ready } = useToken()
  return useQuery<Position[]>({
    queryKey: VIRTUAL_KEY.positions(opts.market, opts.includeClosed),
    queryFn: ({ signal }) =>
      fetchPositions(token, opts, signal),
    enabled: ready,
    retry: 0,
    staleTime: 10_000,
  })
}

export function useEquityCurves(days = 30) {
  const { token, ready } = useToken()
  return useQuery<EquityCurves>({
    queryKey: VIRTUAL_KEY.equityCurves(days),
    queryFn: ({ signal }) => fetchEquityCurves(token, days, signal),
    enabled: ready,
    retry: 0,
    staleTime: 30_000,
  })
}
