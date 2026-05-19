'use client'

/**
 * 右栏:自选股(M0 demo 列表 · Task 4 实装完整 watchlist)+ AI 决策卡占位(M1)。
 */

import { cn } from '@/lib/utils'
import { DEMO_SYMBOLS_BY_MARKET, useWorkbenchStore } from '@/lib/store/workbench-store'
import { VirtualBadge } from '@/components/ui/virtual-badge'

export function WatchlistColumn() {
  const market = useWorkbenchStore((s) => s.market)
  const symbol = useWorkbenchStore((s) => s.symbol)
  const setSymbol = useWorkbenchStore((s) => s.setSymbol)
  const symbols = DEMO_SYMBOLS_BY_MARKET[market]

  return (
    <aside className="flex w-[280px] shrink-0 flex-col border-l border-midas-red bg-background">
      {/* 上半:自选股列表 */}
      <section className="flex-1 overflow-y-auto p-3">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-serif text-sm font-bold text-foreground">自选股</h2>
          <span className="text-[10px] text-muted-foreground/70">M0 demo · Task 4 完整版</span>
        </div>
        <ul className="space-y-1">
          {symbols.map((s) => (
            <li key={s.symbol}>
              <button
                type="button"
                onClick={() => setSymbol(s.symbol)}
                className={cn(
                  'flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition-colors',
                  s.symbol === symbol
                    ? 'border-midas-red bg-midas-red-glow'
                    : 'border-paper bg-cream hover:border-midas-red/40',
                )}
              >
                <span className="font-mono text-xs text-foreground">{s.symbol}</span>
                <span className="text-xs text-muted-foreground">{s.name}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* 分隔 */}
      <div className="border-t border-paper" />

      {/* 下半:AI 决策卡占位(M1 实装) */}
      <section className="p-3">
        <div className="rounded-md border border-dashed border-paper bg-cream p-4 text-center">
          <div className="mb-2 flex justify-center">
            <VirtualBadge size="sm" />
          </div>
          <p className="font-serif text-sm font-bold text-foreground">AI 决策卡</p>
          <p className="mt-1 text-xs text-muted-foreground/70">M1 待实装(缠论 + LLM)</p>
        </div>
      </section>
    </aside>
  )
}
