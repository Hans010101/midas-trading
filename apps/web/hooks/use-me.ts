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
