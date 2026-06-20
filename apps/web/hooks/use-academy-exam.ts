/**
 * 模块结业测验 TanStack Query hooks · 训练营 B 期刀2。
 *
 * - useExamResults:各模块结业状态(登录才发请求 · 供结业徽章)。
 * - useExamQuestions:某模块结业测验题(无答案)。
 * - useSubmitExam:提交判分(mutation)· 成功后 invalidate 结业状态(徽章即时更新)。
 * ★成绩存后端(非 localStorage);retry 0(项目铁律)。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { useMemo } from 'react'

import {
  type ExamQuestionsResponse,
  type ExamResultsResponse,
  fetchExamQuestions,
  fetchExamResults,
  submitExam,
} from '@/lib/api/academy-exam'

const RESULTS_KEY = ['academy-exam-results']

export function useExamResults() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const isLoggedIn = !!token

  const query = useQuery<ExamResultsResponse>({
    queryKey: [...RESULTS_KEY, token],
    queryFn: ({ signal }) => fetchExamResults(token, signal),
    enabled: isLoggedIn,
    retry: 0,
    staleTime: 30_000,
  })

  // 已结业模块集(stage → 曾达标)· 供徽章 O(1) 查
  const passedSet = useMemo(
    () => new Set((query.data?.results ?? []).filter((r) => r.passed).map((r) => r.stage)),
    [query.data],
  )

  return { ...query, passedSet, isLoggedIn }
}

export function useExamQuestions(stage: string, enabled: boolean) {
  return useQuery<ExamQuestionsResponse>({
    queryKey: ['academy-exam-questions', stage],
    queryFn: ({ signal }) => fetchExamQuestions(stage, signal),
    enabled,
    retry: 0,
    staleTime: 60_000,
  })
}

export function useSubmitExam() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({ stage, answers }: { stage: string; answers: number[] }) => {
      if (!token) throw new Error('未登录')
      return submitExam(stage, answers, token)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: RESULTS_KEY })
    },
  })
}
