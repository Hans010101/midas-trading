'use client'

/**
 * 我的 AI 额度(会员刀2)· 三处共用(沙盘 / 回测 / profile)。
 * 消耗动作(诊断/发起回测)后调 invalidate 让"剩 N 次"即时刷新。
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import { fetchQuotaMe } from '@/lib/api/quota'

export const QUOTA_QUERY_KEY = ['quota-me'] as const

export function useQuota() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useQuery({
    queryKey: QUOTA_QUERY_KEY,
    queryFn: ({ signal }) => fetchQuotaMe(token, signal),
    enabled: token !== '',
    staleTime: 30_000, // 额度是慢变数据 · 消耗后由 invalidate 主动刷新
  })
}

export function useInvalidateQuota() {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: QUOTA_QUERY_KEY })
}
