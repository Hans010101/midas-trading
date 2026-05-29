/**
 * 飞书绑定 TanStack Query hooks · ADR 0032 阶段三(对称 use-telegram)。
 *
 * retry: 0(项目铁律)。解绑成功后让通知配置 query 失效,刷新「已绑定」状态。
 */

'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import { NOTIFICATIONS_KEY } from '@/hooks/use-notifications'
import {
  createFeishuBindToken,
  type FeishuBindTokenResult,
  unbindFeishu,
} from '@/lib/api/feishu'

function useToken() {
  const { data: session } = useSession()
  return session?.accessToken ?? ''
}

export function useCreateFeishuBindToken() {
  const token = useToken()
  return useMutation<FeishuBindTokenResult, Error>({
    mutationFn: () => createFeishuBindToken(token),
    retry: 0,
  })
}

export function useUnbindFeishu() {
  const token = useToken()
  const queryClient = useQueryClient()
  return useMutation<void, Error>({
    mutationFn: () => unbindFeishu(token),
    retry: 0,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY.config })
    },
  })
}
