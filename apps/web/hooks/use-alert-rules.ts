/**
 * 告警规则 hooks · 0026 G5 · retry 0(项目铁律)。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  type AlertRule,
  type AlertRuleCreate,
  type ApplyRecommendedResult,
  type IndicatorMeta,
  applyRecommended,
  createAlertRule,
  deleteAlertRule,
  fetchAlertRules,
  fetchIndicators,
  setAlertRuleEnabled,
} from '@/lib/api/alert-rules'

const RULES_KEY = ['alert-rules'] as const
const INDICATORS_KEY = ['alert-indicators'] as const

function useToken() {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function useIndicators() {
  const { token, ready } = useToken()
  return useQuery<IndicatorMeta[]>({
    queryKey: INDICATORS_KEY,
    queryFn: ({ signal }) => fetchIndicators(token, signal),
    enabled: ready,
    retry: 0,
    staleTime: 5 * 60_000, // 指标目录基本不变
  })
}

export function useAlertRules() {
  const { token, ready } = useToken()
  return useQuery<AlertRule[]>({
    queryKey: RULES_KEY,
    queryFn: ({ signal }) => fetchAlertRules(token, signal),
    enabled: ready,
    retry: 0,
    staleTime: 15_000,
  })
}

export function useCreateAlertRule() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<AlertRule, Error, AlertRuleCreate>({
    mutationFn: (body) => createAlertRule(token, body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: RULES_KEY }),
  })
}

export function useSetAlertRuleEnabled() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<AlertRule, Error, { id: number; enabled: boolean }>({
    mutationFn: ({ id, enabled }) => setAlertRuleEnabled(token, id, enabled),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: RULES_KEY }),
  })
}

export function useDeleteAlertRule() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<void, Error, number>({
    mutationFn: (id) => deleteAlertRule(token, id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: RULES_KEY }),
  })
}

export function useApplyRecommended() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<ApplyRecommendedResult, Error, void>({
    mutationFn: () => applyRecommended(token),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: RULES_KEY }),
  })
}
