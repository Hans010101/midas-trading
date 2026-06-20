'use client'

/**
 * 管理员 · 单篇市场周报复核 / 编辑 / 批准(P2)。
 *
 * ★ admin 内部页 · 用 [id] 动态段(零[id] 红线只约束【公开页】· admin 内部页可用 · 同 /admin/users/[id])。
 * ★ 安全边界在后端 AdminDep(403):普通用户手输 URL → 后端 403 → 降级提示。
 * 功能:看正文 → 编辑 title/content(内容立项前 admin 也能手填专业内容)→ 批准(draft→approved)。
 * ★ 发送是第二刀,本页不做。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { useEffect, useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import {
  AdminApiError,
  approveAdminReport,
  fetchAdminReport,
  updateAdminReport,
} from '@/lib/api/admin'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  approved: '已批准',
  sent: '已发送',
}

export default function AdminReportDetailPage() {
  const params = useParams<{ id: string }>()
  const reportId = Number(params.id)
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['admin-report', reportId],
    queryFn: ({ signal }) => fetchAdminReport(token, reportId, signal),
    enabled: token !== '' && Number.isFinite(reportId),
  })

  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [savedHint, setSavedHint] = useState<string | null>(null)

  // 数据到了 / 切换报告 → 同步到本地可编辑态
  useEffect(() => {
    if (query.data) {
      setTitle(query.data.title)
      setContent(query.data.content)
    }
  }, [query.data])

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['admin-report', reportId] })
    void queryClient.invalidateQueries({ queryKey: ['admin-reports'] })
  }

  const saveMutation = useMutation({
    mutationFn: () => updateAdminReport(token, reportId, { title, content }),
    onSuccess: () => {
      setSavedHint('已保存')
      invalidate()
    },
  })

  const approveMutation = useMutation({
    mutationFn: () => approveAdminReport(token, reportId),
    onSuccess: invalidate,
  })

  const forbidden = query.error instanceof AdminApiError && query.error.status === 403
  const notFound = query.error instanceof AdminApiError && query.error.status === 404
  const report = query.data
  const isDraft = report?.status === 'draft'
  const isSent = report?.status === 'sent'

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-4xl px-6 py-8">
        <div className="mb-4 flex items-center gap-3">
          <Link href="/admin/reports" className="text-sm text-muted-foreground hover:text-foreground">
            ← 周报列表
          </Link>
          <h1 className="font-serif text-xl font-bold">报告复核</h1>
        </div>
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
        ) : notFound ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center text-sm text-muted-foreground shadow-sm">
            报告不存在或已删除。
          </div>
        ) : !report ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center text-sm text-muted-foreground shadow-sm">
            加载中…
          </div>
        ) : (
          <div className="rounded-lg border border-paper bg-cream p-6 shadow-sm">
            {/* 状态 + 周期 */}
            <div className="mb-4 flex items-center gap-3 text-xs text-muted-foreground">
              <span
                className={
                  isDraft
                    ? 'rounded px-2 py-0.5 text-muted-foreground'
                    : 'rounded bg-gold/10 px-2 py-0.5 text-gold'
                }
              >
                状态:{STATUS_LABEL[report.status] ?? report.status}
              </span>
              {report.period_start && report.period_end && (
                <span>
                  周期 {report.period_start} ~ {report.period_end}
                </span>
              )}
            </div>

            {/* 标题(可编辑)*/}
            <label className="mb-1 block text-xs text-muted-foreground">标题</label>
            <input
              type="text"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value)
                setSavedHint(null)
              }}
              disabled={isSent}
              className="mb-4 w-full rounded-md border border-paper bg-background px-3 py-2 text-sm disabled:opacity-60"
            />

            {/* 正文(可编辑)· 内容立项前 admin 可手填专业内容 */}
            <label className="mb-1 block text-xs text-muted-foreground">
              正文(★当前为占位内容 · 待内容立项替换专业 prompt;此前 admin 可手动编辑)
            </label>
            <textarea
              value={content}
              onChange={(e) => {
                setContent(e.target.value)
                setSavedHint(null)
              }}
              disabled={isSent}
              rows={16}
              className="w-full rounded-md border border-paper bg-background px-3 py-2 font-mono text-sm leading-relaxed disabled:opacity-60"
            />

            {/* 操作 */}
            <div className="mt-4 flex items-center gap-3">
              <button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending || isSent}
                className="rounded-md border border-midas-red px-4 py-1.5 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow/40 disabled:opacity-50"
              >
                {saveMutation.isPending ? '保存中…' : '保存'}
              </button>
              {isDraft && (
                <button
                  type="button"
                  onClick={() => approveMutation.mutate()}
                  disabled={approveMutation.isPending}
                  className="rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-midas-red-deep disabled:opacity-50"
                >
                  {approveMutation.isPending ? '批准中…' : '批准报告'}
                </button>
              )}
              {savedHint && <span className="text-xs text-gold">{savedHint}</span>}
              {saveMutation.isError && (
                <span className="text-xs text-midas-red">
                  保存失败:
                  {saveMutation.error instanceof AdminApiError
                    ? saveMutation.error.detail
                    : '重试'}
                </span>
              )}
              {approveMutation.isError && (
                <span className="text-xs text-midas-red">
                  批准失败:
                  {approveMutation.error instanceof AdminApiError
                    ? approveMutation.error.detail
                    : '重试'}
                </span>
              )}
            </div>
            {!isDraft && !isSent && (
              <p className="mt-3 text-xs text-muted-foreground">
                ★ 已批准 · 发送给订阅用户是第二刀(本期未做)。
              </p>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
