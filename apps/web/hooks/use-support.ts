'use client'

/**
 * 支付工单 hooks(support 模块)· 提交工单(multipart)。
 * 🔴 红线:前端只提交 · token 从 next-auth session 取(与 use-payment 同范式)。
 */

import { useMutation } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  submitTicket,
  type SubmitTicketInput,
  type TicketCreateOut,
} from '@/lib/api/support'

export function useSubmitTicket() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useMutation<TicketCreateOut, Error, SubmitTicketInput>({
    mutationFn: (input) => submitTicket(token, input),
  })
}
