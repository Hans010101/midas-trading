/**
 * Bot 下单后台预设 hooks · 0026 G5 · retry 0(项目铁律)。
 */

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  type BotPreset,
  type BotPresetUpdate,
  fetchBotPreset,
  updateBotPreset,
} from '@/lib/api/bot-preset'

const BOT_PRESET_KEY = ['bot-preset'] as const

function useToken() {
  const { data: session, status } = useSession()
  return {
    token: session?.accessToken ?? '',
    ready: status === 'authenticated' && Boolean(session?.accessToken),
  }
}

export function useBotPreset() {
  const { token, ready } = useToken()
  return useQuery<BotPreset>({
    queryKey: BOT_PRESET_KEY,
    queryFn: ({ signal }) => fetchBotPreset(token, signal),
    enabled: ready,
    retry: 0,
    staleTime: 30_000,
  })
}

export function useSaveBotPreset() {
  const queryClient = useQueryClient()
  const { token } = useToken()
  return useMutation<BotPreset, Error, BotPresetUpdate>({
    mutationFn: (payload) => updateBotPreset(token, payload),
    onSuccess: (data) => queryClient.setQueryData(BOT_PRESET_KEY, data),
  })
}
