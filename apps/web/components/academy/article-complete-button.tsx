'use client'

/**
 * 文章页「标记学完」交互 · 训练营 B 期刀1(client)。
 *
 * 登录 → toggle 按钮(未学完→标记 / 已学完→点击取消)· 完成态用 success 绿(#0F6E5F · 与涨跌解耦)。
 * 未登录 → 引导登录(不强制 · 浏览不受影响)。进度存后端(刷新保留),不用 localStorage。
 */

import { CheckCircle2, Circle } from 'lucide-react'
import Link from 'next/link'

import { useAcademyProgress, useToggleComplete } from '@/hooks/use-academy-progress'
import { cn } from '@/lib/utils'

export function ArticleCompleteButton({ slug }: { slug: string }) {
  const { completedSet, isLoggedIn, isLoading } = useAcademyProgress()
  const toggle = useToggleComplete()
  const done = completedSet.has(slug)

  if (!isLoggedIn) {
    return (
      <div className="mt-10 flex items-center justify-between gap-3 rounded-lg border border-dashed border-paper bg-surface-subtle px-4 py-3">
        <span className="text-sm text-muted-foreground">登录后可标记学完、记录学习进度</span>
        <Link
          href="/login"
          className="shrink-0 rounded-md border border-midas-red/40 px-3 py-1.5 text-sm font-medium text-midas-red transition-colors hover:bg-midas-red-glow"
        >
          去登录
        </Link>
      </div>
    )
  }

  return (
    <div className="mt-10">
      <button
        type="button"
        disabled={toggle.isPending || isLoading}
        onClick={() => toggle.mutate({ slug, currentlyCompleted: done })}
        aria-pressed={done}
        className={cn(
          'inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50',
          done
            ? 'border-success bg-success/10 text-success'
            : 'border-paper text-muted-foreground hover:border-success/50 hover:text-success',
        )}
      >
        {done ? <CheckCircle2 className="h-4 w-4" /> : <Circle className="h-4 w-4" />}
        {toggle.isPending ? '处理中…' : done ? '已学完 · 点击取消' : '标记已学完'}
      </button>
    </div>
  )
}
