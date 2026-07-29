'use client'

/**
 * 研究室二级切换条 · 「AI 沙盘助手 | 策略回测」(沙盘在左 · 研究室默认工具)。
 *
 * 范式照 app/crypto-market/page.tsx 顶部 framed-segment 按钮组;
 * 高亮:/lab 精确匹配亮回测键(防 /lab/assistant 误亮),/lab/assistant 前缀亮沙盘键
 * (exact/startsWith 标志跟 item 走 · 与数组顺序无关)。
 * 顶部导航 MarketSwitcher 的 onLab=startsWith('/lab') 已天然覆盖子页,这里零联动。
 */

import { usePathname, useRouter } from 'next/navigation'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { cn } from '@/lib/utils'

const TOOLS = [
  { path: '/lab/assistant', zh: 'AI 沙盘助手', en: 'AI Sandbox Assistant', exact: false },
  { path: '/lab', zh: '策略回测', en: 'Strategy Backtest', exact: true },
] as const

export function LabNav() {
  const { locale } = useRuntimeLocale()
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
            {t[locale]}
          </button>
        )
      })}
    </div>
  )
}
