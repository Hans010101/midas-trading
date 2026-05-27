/**
 * Telegram 绑定 TanStack Query hooks · 0025 M1-G G3。
 *
 * retry: 0(项目铁律)。解绑成功后让通知配置 query 失效,刷新「已绑定」状态。
 */

'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import { NOTIFICATIONS_KEY } from '@/hooks/use-notifications'
import {
  type BindTokenResult,
  createBindToken,
  unbindTelegram,
} from '@/lib/api/telegram'

function useToken() {
  const { data: session } = useSession()
  return session?.accessToken ?? ''
}

export function useCreateBindToken() {
  const token = useToken()
  return useMutation<BindTokenResult, Error>({
    mutationFn: () => createBindToken(token),
    retry: 0,
  })
}

export function useUnbindTelegram() {
  const token = useToken()
  const queryClient = useQueryClient()
  return useMutation<void, Error>({
    mutationFn: () => unbindTelegram(token),
    retry: 0,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY.config })
    },
  })
}
