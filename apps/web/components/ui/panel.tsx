import type { HTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

/**
 * Panel · 统一卡片/面板 recipe(0022 §3.2)。
 *
 * 标准卡片容器 = rounded-lg + border-paper + bg-surface-card + shadow-sm。
 * padding 三档:sm(p-3 紧凑)/ md(p-4 默认)/ lg(p-5 宽松)。
 * variant:default(常规)/ accent(选中/强调 · 红边)/ dashed(引导/未激活 · 虚线金边,无阴影)。
 *
 * 用于收口存量手搓卡片(bg-cream/border-paper/rounded-lg 各处不一)· 业务侧只用本组件。
 * (不动现有 shadcn Card —— 那个已被 ai-decision-card 使用;本组件是统一后的标准卡。)
 */
type PanelPadding = 'sm' | 'md' | 'lg'
type PanelVariant = 'default' | 'accent' | 'dashed'

const PADDING: Record<PanelPadding, string> = {
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-5',
}
const VARIANT: Record<PanelVariant, string> = {
  default: 'border-paper bg-surface-card shadow-sm',
  accent: 'border-midas-red bg-surface-card shadow-sm',
  dashed: 'border-dashed border-gold/60 bg-gold/5',
}

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  padding?: PanelPadding
  variant?: PanelVariant
}

export function Panel({
  padding = 'md',
  variant = 'default',
  className,
  ...props
}: PanelProps) {
  return (
    <div
      className={cn('rounded-lg border', VARIANT[variant], PADDING[padding], className)}
      {...props}
    />
  )
}
