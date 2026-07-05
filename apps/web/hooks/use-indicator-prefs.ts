/**
 * 指标偏好 hooks(做T线前端)· retry 0(项目铁律)。
 *
 * useIndicatorPrefs:登录后取偏好(未登录 disabled → 无数据 → 做T 视为 OFF · 暗发布默认隐藏)。
 * useSaveIndicatorPrefs:PATCH 部分更新 · 成功后写回 query 缓存(即时反映)。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  fetchIndicatorPrefs,
  type IndicatorPrefs,
  type IndicatorPrefsUpdate,
  updateIndicatorPrefs,
} from '@/lib/api/indicator-prefs'

const INDICATOR_PREFS_KEY = ['indicator-prefs'] as const

function useToken() {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function useIndicatorPrefs() {
  const { token, ready } = useToken()
  return useQuery<IndicatorPrefs>({
    queryKey: INDICATOR_PREFS_KEY,
    queryFn: ({ signal }) => fetchIndicatorPrefs(token, signal),
    enabled: ready,
    retry: 0,
    staleTime: 60_000,
  })
}

export function useSaveIndicatorPrefs() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<IndicatorPrefs, Error, IndicatorPrefsUpdate>({
    mutationFn: (payload) => updateIndicatorPrefs(token, payload),
    onSuccess: (data) => queryClient.setQueryData(INDICATOR_PREFS_KEY, data),
  })
}
