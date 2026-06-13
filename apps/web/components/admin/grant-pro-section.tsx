'use client'

/**
 * 管理员调权益区(用户管理刀3b-1 · 写操作)。
 *
 * 选周期(月/季/年)+ 备注 → 「授予/延长 Pro」→ ★ 二次确认弹框 → POST /grant →
 * 成功 toast + 详情刷新(onGranted)。🔴 只调 grant 端点(后端只写 subscription+审计)。
 */

import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { grantPro } from '@/lib/api/admin'

const PERIODS = [
  { key: 'month', label: '月卡(30天)', days: 30 },
  { key: 'quarter', label: '季卡(90天)', days: 90 },
  { key: 'year', label: '年卡(365天)', days: 365 },
] as const

export function GrantProSection({
  userId,
  email,
  token,
  onGranted,
}: {
  userId: string
  email: string
  token: string
  onGranted: () => void
}) {
  const [period, setPeriod] = useState<'month' | 'quarter' | 'year'>('month')
  const [note, setNote] = useState('')
  const [confirming, setConfirming] = useState(false)

  const days = PERIODS.find((p) => p.key === period)?.days ?? 30

  const grant = useMutation({
    mutationFn: () => grantPro(token, userId, { period, note: note.trim() || null }),
    onSuccess: (res) => {
      toast.success(`已授予 ${res.days_added} 天 Pro`)
      setConfirming(false)
      setNote('')
      onGranted()
    },
    onError: () => {
      toast.error('授予失败,请重试')
      setConfirming(false)
    },
  })

  return (
    <section className="rounded-lg border border-midas-red/30 bg-midas-red-glow/10 p-5">
      <h2 className="mb-3 font-serif text-base font-bold">管理员操作 · 调整权益</h2>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted-foreground">周期</span>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as typeof period)}
            className="min-h-10 rounded-md border border-paper bg-background px-3 text-sm"
          >
            {PERIODS.map((p) => (
              <option key={p.key} value={p.key}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="flex-1 text-sm">
          <span className="mb-1 block text-xs text-muted-foreground">备注(可选)</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={200}
            placeholder="如:补偿 / VIP 客户"
            className="min-h-10 w-full rounded-md border border-paper bg-background px-3 text-sm"
          />
        </label>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={grant.isPending}
          className="min-h-10 rounded-md bg-midas-red px-5 text-sm font-medium text-white transition-colors hover:bg-midas-red/90 disabled:opacity-60"
        >
          授予 / 延长 Pro
        </button>
      </div>

      {/* ★ 二次确认弹框 */}
      {confirming && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => !grant.isPending && setConfirming(false)}
        >
          <div
            className="w-full max-w-sm rounded-lg bg-background p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-2 font-serif text-base font-bold">确认授予</h3>
            <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
              将给 <span className="font-mono text-foreground">{email}</span> 授予/延长
              <span className="font-bold text-midas-red"> {days} 天 Pro</span>,确认?
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={grant.isPending}
                className="min-h-10 rounded-md border border-paper px-4 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => grant.mutate()}
                disabled={grant.isPending}
                className="min-h-10 rounded-md bg-midas-red px-5 text-sm font-medium text-white transition-colors hover:bg-midas-red/90 disabled:opacity-60"
              >
                {grant.isPending ? '授予中…' : '确认授予'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
