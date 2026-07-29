'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useState } from 'react'
import { toast } from 'sonner'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import {
  AdminApiError,
  fetchAdminSupportTickets,
  type SupportTicketStatus,
  updateAdminSupportTicket,
} from '@/lib/api/admin'
import { createdAtText } from '@/lib/admin-view'

const STATUS_LABEL: Record<SupportTicketStatus, string> = {
  open: '待处理',
  resolved: '已解决',
  closed: '已关闭',
}

const CATEGORY_LABEL: Record<string, string> = {
  not_received: '未收到通知',
  duplicate_charge: '重复扣费',
  activation_failed: '功能异常',
  other: '其他',
}

export default function AdminSupportTicketsPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<SupportTicketStatus | undefined>('open')
  const query = useQuery({
    queryKey: ['admin-support-tickets', status],
    queryFn: ({ signal }) =>
      fetchAdminSupportTickets(token, { status }, signal),
    enabled: token !== '',
  })
  const update = useMutation({
    mutationFn: ({
      ticketId,
      nextStatus,
    }: {
      ticketId: number
      nextStatus: SupportTicketStatus
    }) => updateAdminSupportTicket(token, ticketId, nextStatus),
    onSuccess: () => {
      toast.success('工单状态已更新')
      void queryClient.invalidateQueries({
        queryKey: ['admin-support-tickets'],
      })
      void queryClient.invalidateQueries({ queryKey: ['admin-overview'] })
    },
    onError: () => toast.error('更新失败，请重试'),
  })
  const forbidden =
    query.error instanceof AdminApiError && query.error.status === 403

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <AdminNav />
        {forbidden ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center shadow-sm">
            <p className="text-sm text-muted-foreground">该页面仅管理员可见。</p>
            <Link
              href="/global"
              className="mt-3 inline-block rounded-md bg-midas-red px-4 py-1.5 text-sm text-white"
            >
              返回首页
            </Link>
          </div>
        ) : (
          <>
            <div className="mb-4 flex gap-2">
              {([
                [undefined, '全部'],
                ['open', '待处理'],
                ['resolved', '已解决'],
                ['closed', '已关闭'],
              ] as const).map(([value, label]) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => setStatus(value)}
                  className={
                    status === value
                      ? 'rounded-md bg-midas-red px-3 py-1.5 text-sm text-white'
                      : 'rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground'
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="space-y-3">
              {(query.data?.items ?? []).map((ticket) => (
                <article
                  key={ticket.id}
                  className="rounded-lg border border-paper bg-cream p-5 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="font-mono text-sm font-bold">
                        #{ticket.id} · {CATEGORY_LABEL[ticket.category] ?? ticket.category}
                      </h2>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {ticket.account_email} · {createdAtText(ticket.created_at)}
                      </p>
                    </div>
                    <select
                      aria-label={`工单 ${ticket.id} 状态`}
                      value={ticket.status}
                      disabled={update.isPending}
                      onChange={(event) =>
                        update.mutate({
                          ticketId: ticket.id,
                          nextStatus: event.target.value as SupportTicketStatus,
                        })}
                      className="rounded-md border border-paper bg-background px-2 py-1.5 text-sm"
                    >
                      {Object.entries(STATUS_LABEL).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">
                    {ticket.description}
                  </p>
                  <p className="mt-3 text-xs text-muted-foreground">
                    联系邮箱：{ticket.contact_email}
                    {ticket.related_order_id
                      ? ` · 关联编号：${ticket.related_order_id}`
                      : ''}
                    {ticket.image_count > 0
                      ? ` · 附件 ${ticket.image_count} 张`
                      : ''}
                  </p>
                </article>
              ))}
              {query.status === 'pending' && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  加载中…
                </p>
              )}
              {query.status === 'error' && !forbidden && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  加载失败，请稍后重试。
                </p>
              )}
              {query.isSuccess && query.data.items.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  当前没有工单。
                </p>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
