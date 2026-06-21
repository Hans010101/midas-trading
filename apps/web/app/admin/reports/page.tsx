'use client'

/**
 * 管理员 · 市场周报复核列表(P2)。
 *
 * ★ 安全边界在后端 AdminDep(403):数据全来自 admin API,普通用户手输 URL → 后端 403 → 降级提示。
 * 功能:列表(按 status 筛)+ ★手动触发生成一篇草稿(测试用 · 不必等周一 beat)+ 点进复核。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { ReportMaterialsPanel } from '@/components/admin/report-materials-panel'
import { TopNav } from '@/components/layout/top-nav'
import {
  AdminApiError,
  fetchAdminReports,
  generateAdminReport,
  type ReportListItem,
} from '@/lib/api/admin'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  approved: '已批准',
  sent: '已发送',
}

function statusClass(status: string): string {
  if (status === 'approved') return 'text-gold border border-gold/30 bg-gold/10'
  if (status === 'sent') return 'text-midas-red border border-midas-red/30 bg-midas-red-glow/40'
  return 'text-muted-foreground border border-paper bg-paper/50' // draft
}

const FILTERS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'draft', label: '草稿' },
  { value: 'approved', label: '已批准' },
  { value: 'sent', label: '已发送' },
]

export default function AdminReportsPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('')

  const query = useQuery({
    queryKey: ['admin-reports', statusFilter],
    queryFn: ({ signal }) =>
      fetchAdminReports(token, { status: statusFilter || undefined }, signal),
    enabled: token !== '',
  })

  const genMutation = useMutation({
    mutationFn: () => generateAdminReport(token),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-reports'] })
    },
  })

  const forbidden = query.error instanceof AdminApiError && query.error.status === 403
  const items: ReportListItem[] = query.data?.items ?? []

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="font-serif text-xl font-bold">市场周报</h1>
          <button
            type="button"
            onClick={() => genMutation.mutate()}
            disabled={genMutation.isPending || token === ''}
            className="rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:opacity-50"
          >
            {genMutation.isPending ? '生成中…' : '+ 手动生成草稿'}
          </button>
        </div>
        <AdminNav />

        {genMutation.isError && (
          <p className="mb-3 text-xs text-midas-red">
            生成失败:
            {genMutation.error instanceof AdminApiError
              ? genMutation.error.detail
              : '请稍后重试'}
          </p>
        )}

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
        ) : query.status === 'error' ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center text-sm text-muted-foreground shadow-sm">
            加载失败,请稍后重试。
          </div>
        ) : (
          <>
            {/* 本期素材管理(第三刀)· 上传 md/PDF → 注入本期生成 */}
            <ReportMaterialsPanel />

            {/* 状态筛选 */}
            <div className="mb-4 flex items-center gap-2">
              <span className="text-xs text-muted-foreground">状态</span>
              <div className="flex overflow-hidden rounded-md border border-paper text-sm">
                {FILTERS.map((f) => (
                  <button
                    key={f.value}
                    type="button"
                    onClick={() => setStatusFilter(f.value)}
                    className={
                      statusFilter === f.value
                        ? 'bg-midas-red px-3 py-1.5 font-medium text-white'
                        : 'px-3 py-1.5 text-muted-foreground transition-colors hover:bg-midas-red-glow/50'
                    }
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            {items.length === 0 ? (
              <div className="rounded-lg border border-paper bg-cream p-8 text-center text-sm text-muted-foreground shadow-sm">
                暂无报告。点右上角「手动生成草稿」试试,或等每周一定时生成。
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-paper bg-cream shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-paper text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2 font-medium">标题</th>
                      <th className="px-4 py-2 font-medium">状态</th>
                      <th className="px-4 py-2 font-medium">创建时间</th>
                      <th className="px-4 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((r) => (
                      <tr key={r.id} className="border-b border-paper/60 last:border-0">
                        <td className="px-4 py-3 text-foreground">{r.title}</td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded px-2 py-0.5 text-[11px] leading-tight ${statusClass(r.status)}`}
                          >
                            {STATUS_LABEL[r.status] ?? r.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                          {r.created_at.slice(0, 16).replace('T', ' ')}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Link
                            href={`/admin/reports/${r.id}`}
                            className="text-sm text-midas-red transition-opacity hover:opacity-80"
                          >
                            复核 →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
