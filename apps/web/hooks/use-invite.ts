'use client'

/**
 * 我的邀请(Phase 1.5 刀B)· /account/invite 页用 · GET /invite/me。
 */

import { useQuery } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import { fetchInviteMe } from '@/lib/api/invite'

export function useInvite() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useQuery({
    queryKey: ['invite-me'],
    queryFn: ({ signal }) => fetchInviteMe(token, signal),
    enabled: token !== '',
    staleTime: 60_000,
  })
}
