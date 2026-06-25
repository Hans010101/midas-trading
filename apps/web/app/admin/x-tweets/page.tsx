'use client'

/**
 * 管理员 · X 营销每日推文(阶段4a · PR-3)。
 *
 * ★ 安全边界后端 AdminDep(403)· 数据全来自 admin API,普通用户手输 URL → 后端 403 → 降级。
 * 流程:点「生成今日推文」→ 后端异步选币+DeepSeek生成+门禁 → 列表展示(★门禁不过的也列,标红不可发)。
 * ★ 止于展示 · 不发 X(发布=4b)· 截图(image_path)PR-4 才有,现阶段不显图。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import { fetchXTweets, generateXTweets, type XTweetItem } from '@/lib/api/x-tweets'

function fmtTime(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(
    d.getHours(),
  ).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function BiasBadge({ bias }: { bias: string }) {
  return (
    <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{bias}</span>
  )
}

function TweetCard({ t }: { t: XTweetItem }) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-mono text-sm font-bold">{t.symbol}</span>
        <BiasBadge bias={t.bias} />
        <span className="ml-auto font-mono text-xs text-muted-foreground">
          {fmtTime(t.created_at)}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{t.tweet_text}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-paper pt-2">
        {t.compliance_passed ? (
          <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
            ✓ 门禁通过
          </span>
        ) : (
          <span className="rounded bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
            ✕ 门禁拦截 · 不可发
          </span>
        )}
        <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {t.status === 'draft' ? '待发' : t.status}
        </span>
        {!t.compliance_passed && t.compliance_reason && (
          <span className="w-full text-xs text-red-600">原因:{t.compliance_reason}</span>
        )}
      </div>
    </div>
  )
}

export default function AdminXTweetsPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  const [note, setNote] = useState<string>('')

  const query = useQuery({
    queryKey: ['admin-x-tweets'],
    queryFn: ({ signal }) => fetchXTweets(token, signal),
    enabled: token !== '',
  })

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['admin-x-tweets'] })

  const genMut = useMutation({
    mutationFn: () => generateXTweets(token),
    onSuccess: (res) => {
      setNote(res.message)
      // ★异步生成约数十秒 · 先刷一次,再延时补刷一次(覆盖 worker 跑完)
      invalidate()
      setTimeout(invalidate, 35000)
    },
    onError: () => setNote('触发失败,请重试'),
  })

  const forbidden = query.isError
  const items: XTweetItem[] = query.data?.items ?? []
  const passed = items.filter((t) => t.compliance_passed).length

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-3xl px-6 py-8">
        <h1 className="mb-4 font-serif text-xl font-bold">每日推文</h1>
        <AdminNav />

        {forbidden ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center shadow-sm">
            <p className="text-sm text-muted-foreground">该页面仅管理员可见。</p>
            <Link
              href="/global"
              className="mt-3 inline-block rounded-md bg-midas-red px-4 py-1.5 text-sm text-white hover:bg-midas-red/90"
            >
              返回首页
            </Link>
          </div>
        ) : (
          <>
            <div className="mb-4 flex items-center gap-3">
              <button
                type="button"
                onClick={() => genMut.mutate()}
                disabled={genMut.isPending || token === ''}
                className="rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white hover:bg-midas-red/90 disabled:opacity-50"
              >
                {genMut.isPending ? '触发中…' : '生成今日推文'}
              </button>
              <button
                type="button"
                onClick={invalidate}
                className="rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
              >
                刷新
              </button>
              <span className="ml-auto text-xs text-muted-foreground">
                共 {items.length} 条 · 门禁通过 {passed} 条 · 仅显最近 24h
              </span>
            </div>

            {note && (
              <p className="mb-4 rounded-md bg-gold/10 px-3 py-2 text-xs text-muted-foreground">
                {note}
              </p>
            )}

            {query.isLoading ? (
              <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
            ) : items.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                还没有推文 · 点「生成今日推文」开始(异步,约数十秒后刷新可见)。
              </p>
            ) : (
              <div className="space-y-3">
                {items.map((t) => (
                  <TweetCard key={t.id} t={t} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
