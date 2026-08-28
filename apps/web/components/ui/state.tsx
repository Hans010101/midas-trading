import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 统一空态 / loading(0022 §3.5)。
 *
 * - LoadingNote:统一 loading 文案「载入中…」+ text-faint · 收口「加载中…/分析中...」各处不一。
 * - EmptyState:统一空态(可选 emoji 图标 + 标题 + 副文案 + 可选 CTA)。
 * 收口存量散落的 loading/空态样式(text-xs/text-sm + muted/60 各处不一)。
 */
export function LoadingNote({
  children = '载入中…',
  className,
}: {
  children?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-center justify-center text-sm text-faint', className)}>
      {children}
    </div>
  )
}

export function DataTimestamp({
  value,
  locale = 'zh',
  className,
}: {
  value?: string | null
  locale?: 'en' | 'zh'
  className?: string
}) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const label = date.toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <time dateTime={value} className={cn('text-[11px] text-muted-foreground/70', className)}>
      {locale === 'en' ? `Data ${label}` : `数据 ${label}`}
    </time>
  )
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
  className,
}: {
  icon?: ReactNode
  title?: ReactNode
  hint?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-paper bg-surface-card p-6 text-center',
        className,
      )}
    >
      {icon != null && <div className="text-3xl opacity-40">{icon}</div>}
      {title != null && (
        <div className="mt-2 font-serif text-sm font-bold text-foreground">{title}</div>
      )}
      {hint != null && <div className="mt-1 text-xs text-muted-foreground/70">{hint}</div>}
      {action != null && <div className="mt-3">{action}</div>}
    </div>
  )
}
