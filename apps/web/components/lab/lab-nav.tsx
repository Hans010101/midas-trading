'use client'

/**
 * 研究室二级切换条 · 「策略回测 | 结构分析助手」(助手第3刀)。
 *
 * 范式照 app/crypto-market/page.tsx 顶部 framed-segment 按钮组;
 * 高亮:/lab 精确匹配亮回测键(防 /lab/assistant 误亮),/lab/assistant 前缀亮助手键。
 * 顶部导航 MarketSwitcher 的 onLab=startsWith('/lab') 已天然覆盖子页,这里零联动。
 */

import { usePathname, useRouter } from 'next/navigation'

import { cn } from '@/lib/utils'

const TOOLS = [
  { path: '/lab', label: '策略回测', exact: true },
  { path: '/lab/assistant', label: '结构分析助手', exact: false },
] as const

export function LabNav() {
  const pathname = usePathname()
  const router = useRouter()

  return (
    <div className="mb-6 flex overflow-hidden rounded-md border border-paper text-sm">
      {TOOLS.map((t) => {
        const active = t.exact ? pathname === t.path : (pathname?.startsWith(t.path) ?? false)
        return (
          <button
            key={t.path}
            type="button"
            onClick={() => router.push(t.path)}
            className={cn(
              'px-4 py-1.5 transition-colors',
              active
                ? 'bg-midas-red text-white'
                : 'text-muted-foreground hover:bg-midas-red-glow/50',
            )}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
