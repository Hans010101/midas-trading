/**
 * 通知配置 TanStack Query hooks · 0009 v2。
 *
 * retry: 0(项目铁律)· staleTime 30s(配置变更不频繁)。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  type NotificationConfig,
  type NotificationConfigUpdate,
  type NotificationTestResult,
  fetchNotificationConfig,
  sendTestNotification,
  updateNotificationConfig,
} from '@/lib/api/notifications'

export const NOTIFICATIONS_KEY = {
  config: ['notifications', 'config'] as const,
}

function useToken() {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function useNotificationConfig() {
  const { token, ready } = useToken()
  return useQuery<NotificationConfig>({
    queryKey: NOTIFICATIONS_KEY.config,
    queryFn: ({ signal }) => fetchNotificationConfig(token, signal),
    enabled: ready,
    retry: 0,
    staleTime: 30_000,
  })
}

export function useSaveNotificationConfig() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<NotificationConfig, Error, NotificationConfigUpdate>({
    mutationFn: (update) => updateNotificationConfig(token, update),
    onSuccess: (data) => {
      queryClient.setQueryData(NOTIFICATIONS_KEY.config, data)
    },
  })
}

export function useSendTestNotification() {
  const { token } = useToken()
  return useMutation<NotificationTestResult, Error, 'telegram' | 'feishu'>({
    mutationFn: (channel) => sendTestNotification(token, channel),
  })
}
