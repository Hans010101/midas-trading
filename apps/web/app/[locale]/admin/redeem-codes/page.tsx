'use client'

/**
 * 兑换码管理(兑换码刀2 · /admin/redeem-codes)。
 *
 * 生成区(周期+数量+备注 → POST)+ 本批码展示(复制单/全部)+ 列表(状态色 · 分页)。
 * 🔴 安全边界在后端 AdminDep(403):普通用户手输 URL → 403 降级提示。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy } from 'lucide-react'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useState } from 'react'
import { toast } from 'sonner'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import {
  type GenerateResult,
  RedeemApiError,
  type RedeemPeriod,
  fetchCodes,
  generateCodes,
} from '@/lib/api/redeem'
import {
  PERIOD_OPTIONS,
  joinCodes,
  periodLabel,
  statusClass,
  STATUS_LABEL,
} from '@/lib/redeem-view'

const PAGE_SIZE = 20

function useCopy() {
  const [copied, setCopied] = useState('')
  const copy = async (text: string, tag: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(tag)
      setTimeout(() => setCopied(''), 1800)
    } catch {
      toast.error('复制失败,请手动复制')
    }
  }
  return { copied, copy }
}

export default function AdminRedeemCodesPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  const { copied, copy } = useCopy()

  const [period, setPeriod] = useState<RedeemPeriod>('month')
  const [count, setCount] = useState(10)
  const [note, setNote] = useState('')
  const [batch, setBatch] = useState<GenerateResult | null>(null)
  const [page, setPage] = useState(1)

  const list = useQuery({
    queryKey: ['admin-redeem-codes', page],
    queryFn: ({ signal }) => fetchCodes(token, { page, pageSize: PAGE_SIZE }, signal),
    enabled: token !== '',
  })
  const forbidden = list.error instanceof RedeemApiError && list.error.status === 403

  const gen = useMutation({
    mutationFn: () =>
      generateCodes(token, { period, count, note: note.trim() || null }),
    onSuccess: (res) => {
      setBatch(res)
      toast.success(`已生成 ${res.codes.length} 个${periodLabel(res.period)}`)
      void qc.invalidateQueries({ queryKey: ['admin-redeem-codes'] })
    },
    onError: () => toast.error('生成失败,请重试'),
  })

  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1

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
              className="mt-3 inline-block rounded-md bg-midas-red px-4 py-1.5 text-sm text-white transition-colors hover:bg-midas-red/90"
            >
              返回首页
            </Link>
          </div>
        ) : (
          <>
            {/* 生成区 */}
            <section className="mb-6 rounded-lg border border-paper bg-cream p-5 shadow-sm">
              <h2 className="mb-3 font-serif text-base font-bold">批量生成</h2>
              <div className="flex flex-wrap items-end gap-3">
                <label className="text-sm">
                  <span className="mb-1 block text-xs text-muted-foreground">周期</span>
                  <select
                    value={period}
                    onChange={(e) => setPeriod(e.target.value as RedeemPeriod)}
                    className="min-h-10 rounded-md border border-paper bg-background px-3 text-sm"
                  >
                    {PERIOD_OPTIONS.map((o) => (
                      <option key={o.key} value={o.key}>{o.label}</option>
                    ))}
                  </select>
                </label>
                <label className="text-sm">
                  <span className="mb-1 block text-xs text-muted-foreground">数量(1-100)</span>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={count}
                    onChange={(e) => setCount(Math.min(100, Math.max(1, Number(e.target.value) || 1)))}
                    className="min-h-10 w-28 rounded-md border border-paper bg-background px-3 text-sm"
                  />
                </label>
                <label className="flex-1 text-sm">
                  <span className="mb-1 block text-xs text-muted-foreground">备注(可选)</span>
                  <input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    maxLength={128}
                    placeholder="如:送给 XX / 双十一活动"
                    className="min-h-10 w-full rounded-md border border-paper bg-background px-3 text-sm"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => gen.mutate()}
                  disabled={gen.isPending || token === ''}
                  className="min-h-10 rounded-md bg-midas-red px-5 text-sm font-medium text-white transition-colors hover:bg-midas-red/90 disabled:opacity-60"
                >
                  {gen.isPending ? '生成中…' : '生成'}
                </button>
              </div>

              {/* 本批生成结果 */}
              {batch && (
                <div className="mt-4 rounded-md border border-down/30 bg-down/5 p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-medium text-foreground">
                      本批 {batch.codes.length} 个 · {periodLabel(batch.period)}
                    </span>
                    <button
                      type="button"
                      onClick={() => copy(joinCodes(batch.codes), 'all')}
                      className="inline-flex items-center gap-1.5 rounded border border-paper px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {copied === 'all' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      {copied === 'all' ? '已复制' : '复制全部码'}
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {batch.codes.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => copy(c, c)}
                        title="点击复制"
                        className="rounded bg-surface-subtle px-2 py-1 font-mono text-xs text-foreground transition-colors hover:bg-midas-red-glow/40"
                      >
                        {copied === c ? '已复制' : c}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </section>

            {/* 列表区 */}
            <div className="overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-paper text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2.5 font-normal">兑换码</th>
                    <th className="px-4 py-2.5 font-normal">周期</th>
                    <th className="px-4 py-2.5 font-normal">状态</th>
                    <th className="px-4 py-2.5 font-normal">备注</th>
                    <th className="px-4 py-2.5 font-normal">被谁用</th>
                    <th className="px-4 py-2.5 font-normal">生成时间</th>
                  </tr>
                </thead>
                <tbody>
                  {(list.data?.items ?? []).map((it) => (
                    <tr key={it.code} className="border-b border-paper/60 last:border-0">
                      <td className="px-4 py-2.5">
                        <button
                          type="button"
                          onClick={() => copy(it.code, it.code)}
                          title="点击复制"
                          className="font-mono text-xs transition-colors hover:text-midas-red"
                        >
                          {copied === it.code ? '已复制' : it.code}
                        </button>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">{periodLabel(it.period)}</td>
                      <td className={`px-4 py-2.5 text-xs ${statusClass(it.status)}`}>
                        {STATUS_LABEL[it.status]}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">{it.note ?? '—'}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground/70">
                        {it.redeemed_by_email ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground/70">
                        {new Date(it.created_at).toLocaleDateString('zh-CN')}
                      </td>
                    </tr>
                  ))}
                  {list.status === 'pending' && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-xs text-muted-foreground/60">
                        加载中…
                      </td>
                    </tr>
                  )}
                  {list.status === 'success' && list.data.items.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-xs text-muted-foreground/60">
                        还没有兑换码,用上方生成
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex items-center justify-end gap-2 text-xs">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="min-h-10 rounded border border-paper px-2.5 py-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 lg:min-h-0"
              >
                上一页
              </button>
              <span className="font-mono text-muted-foreground">{page} / {totalPages}</span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="min-h-10 rounded border border-paper px-2.5 py-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 lg:min-h-0"
              >
                下一页
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
