/**
 * AI 沙盘助手(原结构分析助手)TanStack Query hooks · 助手第3刀。
 * 照 hooks/use-backtest.ts:useToken() = useSession().accessToken;diagnose 是 POST → useMutation
 * (照 useCreateBacktest 范式 · 服务端已有 1h/意图分桶缓存,前端不再叠 query 缓存)。
 */

'use client'

import { useMutation } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  type DiagnoseRequest,
  type StructureDiagnosis,
  postDiagnose,
} from '@/lib/api/structure'

function useToken(): { token: string; ready: boolean } {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function useStructureDiagnose(locale: 'en' | 'zh' = 'zh') {
  const { token } = useToken()
  return useMutation<StructureDiagnosis, Error, DiagnoseRequest>({
    mutationFn: (body) => postDiagnose(token, body, locale),
  })
}
