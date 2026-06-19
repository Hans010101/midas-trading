/**
 * 条件单 TanStack Query hooks(ADR 0041 刀3)· 照 use-virtual.ts 范式。
 *
 * retry: 0(项目铁律 · retry 不分层叠加)。
 * 列表 refetchInterval 30s:后端扫描 60s 一轮,30s 轮询下 active→triggered
 * 最迟 ~90s 可见(条件单可挂数天,不照 use-backtest 的 3s 短轮询)。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  type AiPlanOrderInput,
  type ConditionalOrder,
  type ConditionalOrderCreate,
  cancelConditionalOrder,
  listConditionalOrders,
  placeAiPlanOrder,
  postConditionalOrder,
} from '@/lib/api/conditional-order'
import type { ConditionalStatus } from '@/lib/conditional'

export const CONDITIONAL_KEY = {
  list: (status?: ConditionalStatus) => ['conditional-orders', status ?? 'all'] as const,
}

function useToken(): { token: string; ready: boolean } {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function useConditionalOrders(opts: { status?: ConditionalStatus } = {}) {
  const { token, ready } = useToken()
  return useQuery<ConditionalOrder[]>({
    queryKey: CONDITIONAL_KEY.list(opts.status),
    queryFn: ({ signal }) => listConditionalOrders(token, opts, signal),
    enabled: ready,
    retry: 0,
    refetchInterval: 30_000,
    staleTime: 25_000,
  })
}

export function usePlaceConditionalOrder() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<ConditionalOrder, Error, ConditionalOrderCreate>({
    mutationFn: (input) => postConditionalOrder(token, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conditional-orders'] })
    },
  })
}

export function usePlaceAiPlanOrder() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<ConditionalOrder, Error, AiPlanOrderInput>({
    mutationFn: (input) => placeAiPlanOrder(token, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conditional-orders'] })
    },
  })
}

export function useCancelConditionalOrder() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<void, Error, number>({
    mutationFn: (id) => cancelConditionalOrder(token, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conditional-orders'] })
    },
  })
}
