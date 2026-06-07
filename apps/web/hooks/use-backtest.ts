/**
 * 研究室回测 TanStack Query hooks · P1-4d(ADR 0038)。
 *
 * 照 hooks/use-virtual.ts:useToken() = useSession().accessToken + enabled:ready + retry:0(项目铁律)。
 * 轮询(确认报告 D3 标准写法):pending 每 3s 刷新,done/error 停。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  type BacktestCreateRequest,
  type BacktestCreateResponse,
  type BacktestRunListItem,
  type BacktestRunResponse,
  createBacktest,
  getBacktest,
  listBacktests,
} from '@/lib/api/backtest'

export const BACKTEST_KEY = {
  list: ['backtest', 'list'] as const,
  run: (id: number) => ['backtest', 'run', id] as const,
}

function useToken(): { token: string; ready: boolean } {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function useBacktestList() {
  const { token, ready } = useToken()
  return useQuery<BacktestRunListItem[]>({
    queryKey: BACKTEST_KEY.list,
    queryFn: ({ signal }) => listBacktests(token, 50, signal),
    enabled: ready,
    retry: 0,
    staleTime: 10_000,
  })
}

export function useBacktestRun(id: number | null) {
  const { token, ready } = useToken()
  return useQuery<BacktestRunResponse>({
    queryKey: BACKTEST_KEY.run(id ?? -1),
    queryFn: ({ signal }) => getBacktest(token, id as number, signal),
    enabled: ready && id != null && id > 0,
    retry: 0,
    // 轮询:pending 每 3s 刷新,done/error 停(确认报告 D3)。
    refetchInterval: (query) => (query.state.data?.status === 'pending' ? 3000 : false),
  })
}

export function useCreateBacktest() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<BacktestCreateResponse, Error, BacktestCreateRequest>({
    mutationFn: (body) => createBacktest(token, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BACKTEST_KEY.list })
    },
  })
}
