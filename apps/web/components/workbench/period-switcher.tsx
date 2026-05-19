'use client'

/**
 * 周期切换器 · 15m / 1h / 1d / 1w 四 tab(M0 demo 4 档)。
 * 选中态用 midas-red 背景,未选中态 ghost + hover red-glow。
 */

import type { Period } from '@midas/shared'

import { cn } from '@/lib/utils'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

const PERIODS_VISIBLE: ReadonlyArray<{ value: Period; label: string }> = [
  { value: '15m', label: '15 分' },
  { value: '1h', label: '1 小时' },
  { value: '1d', label: '日 K' },
  { value: '1w', label: '周 K' },
]

export function PeriodSwitcher() {
  const period = useWorkbenchStore((s) => s.period)
  const setPeriod = useWorkbenchStore((s) => s.setPeriod)

  return (
    <div className="inline-flex items-center gap-1 rounded-md border border-paper bg-cream p-1">
      {PERIODS_VISIBLE.map((p) => (
        <button
          key={p.value}
          type="button"
          onClick={() => setPeriod(p.value)}
          className={cn(
            'rounded-sm px-3 py-1 text-xs font-medium transition-colors',
            p.value === period
              ? 'bg-midas-red text-primary-foreground'
              : 'text-muted-foreground hover:bg-midas-red-glow hover:text-foreground',
          )}
        >
          {p.label}
        </button>
      ))}
    </div>
  )
}
