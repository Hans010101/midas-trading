'use client'

/**
 * 当前用户资料 hooks · /auth/me 查询 + 改密码 + 头像。token 从 next-auth session 取。
 * 头像更新成功 → invalidate ME_QUERY_KEY → 右上下拉 + 个人中心头像即时刷新。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  changePassword,
  fetchMe,
  setAvatar,
  setLanguage,
  type MeResponse,
} from '@/lib/api/me'

export const ME_QUERY_KEY = ['me'] as const

export function useMe() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useQuery<MeResponse>({
    queryKey: ME_QUERY_KEY,
    queryFn: ({ signal }) => fetchMe(token, signal),
    enabled: token !== '',
    staleTime: 30_000,
  })
}

export function useChangePassword() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useMutation<void, Error, { oldPassword: string; newPassword: string }>({
    mutationFn: ({ oldPassword, newPassword }) =>
      changePassword(token, oldPassword, newPassword),
  })
}

export function useSetAvatar() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  return useMutation<number | null, Error, number>({
    mutationFn: (avatarId) => setAvatar(token, avatarId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  })
}

// ★i18n:写回语言偏好(登录用户跨设备同步)· NEXT_LOCALE cookie 是本设备即时生效层。
//   这里只做后端持久化 · 成功后 invalidate ME 让 language_pref 回显最新。
export function useSetLanguage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  return useMutation<string, Error, 'zh' | 'en'>({
    mutationFn: (language) => setLanguage(token, language),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  })
}
