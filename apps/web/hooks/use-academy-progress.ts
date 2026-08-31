/**
 * 训练营学习进度 TanStack Query hooks · B 期刀1。
 *
 * - useAcademyProgress:拉当前用户进度(登录才发请求 · token 并入 queryKey · 登出即刷新)。
 * - useMarkComplete:标记学完(mutation · 刀1.5 答完小测自动调)· 成功后 invalidate 进度查询。
 * ★ 进度存后端(不用 localStorage);retry 0(项目铁律)。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { useMemo } from 'react'

import {
  type AcademyProgress,
  fetchAcademyProgress,
  markArticleComplete,
} from '@/lib/api/academy-progress'

const PROGRESS_KEY = ['academy-progress']

export function useAcademyProgress() {
  const { data: session, status } = useSession()
  const token = session?.accessToken ?? ''
  const isLoggedIn = status === 'authenticated' && !!token

  const query = useQuery<AcademyProgress>({
    queryKey: [...PROGRESS_KEY, token],
    queryFn: ({ signal }) => fetchAcademyProgress(token, signal),
    enabled: isLoggedIn, // 未登录不发请求(组件只显示 manifest 计数,不显示进度)
    retry: 0,
    staleTime: 30_000,
  })

  // O(1) 查某篇是否已学完(文章页 / 阶列表用)
  const completedSet = useMemo(
    () => new Set(query.data?.completed_slugs ?? []),
    [query.data],
  )

  return { ...query, completedSet, isLoggedIn, isAuthLoading: status === 'loading' }
}

/** 标记学完(刀1.5:答完小测自动调 · 幂等由调用方 shouldAutoMark 守)。 */
export function useMarkComplete() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async (slug: string) => {
      if (!token) throw new Error('未登录')
      await markArticleComplete(slug, token)
    },
    // 标记后刷新进度(prefix 失效 · 覆盖带 token 的 key)→ 阶进度 X/Y 即时 +1
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROGRESS_KEY })
    },
  })
}
