/**
 * 训练营学习进度 TanStack Query hooks · B 期刀1。
 *
 * - useAcademyProgress:拉当前用户进度(登录才发请求 · token 并入 queryKey · 登出即刷新)。
 * - useToggleComplete:标记 / 取消学完(mutation)· 成功后 invalidate 进度查询。
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
  unmarkArticleComplete,
} from '@/lib/api/academy-progress'

const PROGRESS_KEY = ['academy-progress']

export function useAcademyProgress() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const isLoggedIn = !!token

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

  return { ...query, completedSet, isLoggedIn }
}

export function useToggleComplete() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      slug,
      currentlyCompleted,
    }: {
      slug: string
      currentlyCompleted: boolean
    }) => {
      if (!token) throw new Error('未登录')
      if (currentlyCompleted) {
        await unmarkArticleComplete(slug, token)
      } else {
        await markArticleComplete(slug, token)
      }
    },
    // 标记/取消后刷新进度(prefix 失效 · 覆盖带 token 的 key)
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROGRESS_KEY })
    },
  })
}
