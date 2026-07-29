'use client'

import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'

import { revokeUserSessions } from '@/lib/api/admin'

export function SessionSection({
  userId,
  activeSessions,
  token,
  onChanged,
}: {
  userId: string
  activeSessions: number
  token: string
  onChanged: () => void
}) {
  const mutation = useMutation({
    mutationFn: () => revokeUserSessions(token, userId),
    onSuccess: (result) => {
      toast.success(`已撤销 ${result.revoked_sessions} 个会话`)
      onChanged()
    },
    onError: () => toast.error('撤销会话失败，请重试'),
  })

  return (
    <section className="rounded-lg border border-paper bg-surface-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-base font-bold">登录会话</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            当前有效设备：{activeSessions} · 管理员操作会写入审计记录
          </p>
        </div>
        <button
          type="button"
          disabled={activeSessions === 0 || mutation.isPending}
          onClick={() => mutation.mutate()}
          className="min-h-10 rounded-md border border-paper px-4 text-sm text-muted-foreground transition-colors hover:border-midas-red/40 hover:text-midas-red disabled:opacity-40"
        >
          {mutation.isPending ? '撤销中…' : '撤销全部会话'}
        </button>
      </div>
    </section>
  )
}
