'use client'

/**
 * 指标面板 · MA / MACD / RSI / BOLL 四个 toggle。
 * 状态走 useWorkbenchStore,KlineChart 订阅 indicators 自动同步到 chart 实例。
 */

import { cn } from '@/lib/utils'
import { type IndicatorName, useWorkbenchStore } from '@/lib/store/workbench-store'

const INDICATOR_LIST: ReadonlyArray<{ name: IndicatorName; label: string; hint: string }> = [
  { name: 'MA', label: 'MA', hint: '均线 5/10/20/60' },
  { name: 'BOLL', label: 'BOLL', hint: '布林带' },
  { name: 'MACD', label: 'MACD', hint: '副图 · 异同移动平均' },
  { name: 'RSI', label: 'RSI', hint: '副图 · 相对强弱' },
]

export function IndicatorPanel() {
  const indicators = useWorkbenchStore((s) => s.indicators)
  const toggleIndicator = useWorkbenchStore((s) => s.toggleIndicator)

  return (
    <div className="inline-flex items-center gap-1">
      {INDICATOR_LIST.map((ind) => (
        <button
          key={ind.name}
          type="button"
          onClick={() => toggleIndicator(ind.name)}
          title={ind.hint}
          className={cn(
            'rounded-md border px-2.5 py-1 font-mono text-xs transition-colors',
            indicators[ind.name]
              ? 'border-midas-red bg-midas-red-glow text-midas-red'
              : 'border-paper bg-cream text-muted-foreground hover:border-midas-red/40 hover:text-foreground',
          )}
        >
          {ind.label}
        </button>
      ))}
    </div>
  )
}
