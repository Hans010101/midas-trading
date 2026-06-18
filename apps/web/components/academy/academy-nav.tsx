'use client'

/**
 * 训练营二级切换条 · 「训练营首页 | 名词词典」· 范式照 components/lab/lab-nav.tsx 的 framed-segment。
 *
 * 阶的切换在首页卡片点击(不放二级导航,避免 tab 过多);首页 + 词典两个 tab 即可。
 * 高亮:/academy 精确匹配亮首页键(防 /academy/stage 等子页误亮),/academy/glossary 前缀亮词典键
 * (exact / startsWith 标志跟 item 走 · 与数组顺序无关)。
 */

import { usePathname, useRouter } from 'next/navigation'

import { cn } from '@/lib/utils'

const TABS = [
  { path: '/academy', label: '训练营首页', exact: true },
  { path: '/academy/glossary', label: '名词词典', exact: false },
] as const

export function AcademyNav() {
  const pathname = usePathname()
  const router = useRouter()

  return (
    <div className="mb-6 flex overflow-hidden rounded-md border border-paper text-sm">
      {TABS.map((t) => {
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
