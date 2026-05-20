/**
 * Disclaimer 条 · 0012 ADR 红线 ④ · API + UI 双层兜底。
 *
 * 后端 DecisionCardResponse.disclaimer 字段是主防线 · 本组件硬编码兜底:
 * 即使后端没返回 disclaimer(老缓存 / bug),前端也总能显示。
 *
 * 视觉 token:cream 底 + ink-faint 文字 + ⚠ 标识 · 不喧宾夺主但必能看见。
 */

import { AlertTriangle } from 'lucide-react'

import { cn } from '@/lib/utils'

interface Props {
  className?: string
  /** 紧凑模式 · 顶部信号条用 */
  compact?: boolean
}

export function DisclaimerStrip({ className, compact = false }: Props) {
  return (
    <div
      className={cn(
        'flex items-center gap-1 rounded border border-paper bg-cream',
        compact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-[10px]',
        'text-muted-foreground/70',
        className,
      )}
      role="note"
      aria-label="风险提示"
    >
      <AlertTriangle className={compact ? 'h-2.5 w-2.5' : 'h-3 w-3'} />
      <span>仅供参考,不构成投资建议</span>
    </div>
  )
}
