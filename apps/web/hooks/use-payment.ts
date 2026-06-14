'use client'

/**
 * 会员订阅支付 hooks(Phase 2a 刀2)· 建单 + 到账轮询。
 * 🔴 红线:前端只建单 / 查状态 · 开权益由后端回调核验(防伪造四重)· 前端不判付款真伪。
 */

import { useMutation, useQuery } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'

import {
  createPaymentOrder,
  fetchOrderStatus,
  type CreateOrderOut,
  type OrderStatusOut,
  type Period,
} from '@/lib/api/payment'

export function useCreatePaymentOrder() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useMutation<CreateOrderOut, Error, Period>({
    mutationFn: (period) => createPaymentOrder(token, period),
  })
}

/** 订单到账轮询:pending 时每 5s 轮询,paid/expired 停。enabled 由 externalId 控制。 */
export function useOrderStatus(externalId: string | null) {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  return useQuery<OrderStatusOut>({
    queryKey: ['payment-order-status', externalId],
    queryFn: ({ signal }) => fetchOrderStatus(token, externalId as string, signal),
    enabled: token !== '' && externalId != null,
    // 待支付每 5s 轮一次 · 到账(paid)/ 失效(expired)即停
    refetchInterval: (query) =>
      query.state.data?.status === 'pending' ? 5000 : false,
  })
}
