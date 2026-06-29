'use client'

/**
 * 铂金标记区(多账户 PR-1 · 写操作 · superadmin 手动设)· 仿 BanSection 范式。
 *
 * 开通铂金 → 该用户享受【所有 pro 权益】+ 托管交易/智能交易 2 个交易体系(每用户独立账户·体验同管理员)。
 * 二次确认(给权益较重)→ POST /set-platinum → 刷新。🔴 只调 set-platinum 端点(后端写 + 审计)。
 */

import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { setPlatinum } from '@/lib/api/admin'

export function PlatinumSection({
  userId,
  email,
  isPlatinum,
  token,
  onChanged,
}: {
  userId: string
  email: string
  isPlatinum: boolean
  token: string
  onChanged: () => void
}) {
  const [confirming, setConfirming] = useState(false)

  const mut = useMutation({
    mutationFn: () => setPlatinum(token, userId, !isPlatinum),
    onSuccess: (res) => {
      toast.success(res.is_platinum ? '已开通铂金' : '已取消铂金')
      setConfirming(false)
      onChanged()
    },
    onError: () => {
      toast.error('操作失败,请重试')
      setConfirming(false)
    },
  })

  return (
    <section className="rounded-lg border border-paper bg-surface-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-base font-bold">铂金标记</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {isPlatinum
              ? '已开通 · 享受所有 Pro 权益 + 托管交易/智能交易(独立账户)'
              : '未开通 · 普通用户(按订阅判会员)'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={mut.isPending}
          className={
            isPlatinum
              ? 'min-h-10 shrink-0 rounded-md border border-paper px-4 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60'
              : 'min-h-10 shrink-0 rounded-md border border-gold px-4 text-sm font-medium text-gold transition-colors hover:bg-gold/10 disabled:opacity-60'
          }
        >
          {isPlatinum ? '取消铂金' : '开通铂金'}
        </button>
      </div>

      {/* ★ 二次确认(给权益较重) */}
      {confirming && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => !mut.isPending && setConfirming(false)}
        >
          <div
            className="w-full max-w-sm rounded-lg bg-background p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-2 font-serif text-base font-bold">
              {isPlatinum ? '确认取消铂金' : '确认开通铂金'}
            </h3>
            <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
              {isPlatinum ? (
                <>
                  将取消 <span className="font-mono text-foreground">{email}</span> 的铂金标记,
                  收回所有 Pro 权益 + 托管/智能交易访问。
                </>
              ) : (
                <>
                  确认给 <span className="font-mono text-foreground">{email}</span> 开通铂金?
                  <span className="text-gold">
                    该用户将享受所有 Pro 权益 + 托管交易/智能交易(每用户独立账户·体验同管理员)。
                  </span>
                </>
              )}
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={mut.isPending}
                className="min-h-10 rounded-md border border-paper px-4 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => mut.mutate()}
                disabled={mut.isPending}
                className="min-h-10 rounded-md bg-gold px-5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
              >
                {mut.isPending ? '处理中…' : isPlatinum ? '确认取消' : '确认开通'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
