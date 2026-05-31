'use client'

/**
 * 缠论标注开关 · 0011 ADR § 7。
 *
 * 视觉:开 = 中国红填充 + 帝王金徽章;关 = 灰色 outline。
 * 默认关 · 避免新用户被一堆线吓到。
 */

import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'

export function ChanToggle() {
  const enabled = useWorkbenchStore((s) => s.chanEnabled)
  const toggle = useWorkbenchStore((s) => s.toggleChan)

  return (
    <button
      type="button"
      onClick={toggle}
      title={
        enabled
          ? '关闭缠论标注(笔/中枢/分型)'
          : '开启缠论标注(笔/中枢/分型)'
      }
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors',
        enabled
          ? 'bg-midas-red text-white shadow-sm'
          : 'border border-paper text-muted-foreground hover:border-midas-red hover:text-midas-red',
      )}
      aria-pressed={enabled}
    >
      <span className="font-serif text-sm">缠</span>
      <span>{enabled ? '开' : '关'}</span>
      {enabled && (
        <span className="ml-0.5 inline-block h-1.5 w-1.5 rounded-full bg-gold" />
      )}
    </button>
  )
}
