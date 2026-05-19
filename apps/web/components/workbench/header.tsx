'use client'

/**
 * 工作台 Header · Logo + 市场 Tab + 用户菜单占位。
 * 1px 红色 border-bottom 突出"工程师工作面"。
 */

import { MARKETS, type Market } from '@midas/shared'

import { cn } from '@/lib/utils'
import { useWorkbenchStore } from '@/lib/store/workbench-store'

const MARKET_LABEL: Record<Market, string> = {
  cn: 'A 股',
  us: '美股',
  crypto: '加密',
}

export function Header() {
  const market = useWorkbenchStore((s) => s.market)
  const setMarket = useWorkbenchStore((s) => s.setMarket)

  return (
    <header className="h-14 shrink-0 border-b border-midas-red bg-background">
      <div className="flex h-full items-center justify-between px-6">
        <h1 className="font-serif text-xl font-bold text-foreground">
          点金 <span className="text-midas-red">Midas</span>
        </h1>

        <nav className="flex items-center gap-1" aria-label="市场切换">
          {MARKETS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMarket(m)}
              className={cn(
                'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
                m === market
                  ? 'bg-midas-red text-primary-foreground'
                  : 'text-muted-foreground hover:bg-midas-red-glow hover:text-foreground',
              )}
            >
              {MARKET_LABEL[m]}
            </button>
          ))}
        </nav>

        {/* 用户菜单占位 · M0 不实装(NextAuth 是 Task 3+) */}
        <div className="text-xs text-muted-foreground/70">用户菜单 · M0 占位</div>
      </div>
    </header>
  )
}
