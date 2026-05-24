'use client'

/**
 * 市场切换条(A 股 / 美股 / 加密)· 全站共用组件。
 *
 * 从工作台 Header 抽出 · 工作台页 + 加密市场列表页共用同一份。
 *
 * 行为(按当前所在页面自适应,组件自己判断「当前在哪个市场」):
 *  - 在工作台(/workbench):
 *      · A 股 / 美股 → setMarket 工作台内切换(**与抽取前完全一致**,无路由跳转)
 *      · 加密       → 跳 /crypto-market 列表页(B 方案:加密频道 = 列表→详情)
 *      · 选中态     = 工作台 store 的当前 market
 *  - 在任一「市场首页」(/cn-market、/us-market、/crypto-market · 0023 阶段③):
 *      · 点任一市场 → 跳对应市场首页(已在本页则 no-op · 三首页互链)
 *      · 选中态     = 当前所在市场首页
 *
 * 视觉沿用工作台 Header 原市场 Tab 样式(中国红选中态),保证工作台外观不变。
 */

import { usePathname, useRouter } from 'next/navigation'

import { MARKET_LABEL } from '@/lib/format-money'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'
import { MARKETS, type Market } from '@midas/shared'

export function MarketSwitcher({ className }: { className?: string }) {
  const pathname = usePathname()
  const router = useRouter()
  const storeMarket = useWorkbenchStore((s) => s.market)
  const setMarket = useWorkbenchStore((s) => s.setMarket)

  // 当前在哪个「市场首页」(列表/总览页)· 0023 阶段③ 起 A股/美股/加密 三市场首页互链
  const homeMarket: Market | null = pathname?.startsWith('/cn-market')
    ? 'cn'
    : pathname?.startsWith('/us-market')
      ? 'us'
      : pathname?.startsWith('/crypto-market')
        ? 'crypto'
        : null
  const active: Market = homeMarket ?? storeMarket

  function handleSelect(m: Market) {
    // 在任一市场首页:点市场 → 跳对应市场首页(已在本页则 no-op)
    if (homeMarket) {
      if (m === homeMarket) return
      if (m === 'cn') router.push('/cn-market')
      else if (m === 'us') router.push('/us-market')
      else router.push('/crypto-market')
      return
    }
    // 在工作台(/workbench)· 保持抽取前行为(零回归):
    //   加密 → 跳加密列表页;A 股 / 美股 → 工作台内 setMarket 切换(含重置 symbol · 不跳转)
    if (m === 'crypto') {
      router.push('/crypto-market')
      return
    }
    setMarket(m)
  }

  return (
    <nav className={cn('flex items-center gap-1', className)} aria-label="市场切换">
      {MARKETS.map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => handleSelect(m)}
          className={cn(
            'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
            m === active
              ? 'bg-midas-red text-primary-foreground'
              : 'text-muted-foreground hover:bg-midas-red-glow hover:text-foreground',
          )}
        >
          {MARKET_LABEL[m]}
        </button>
      ))}
    </nav>
  )
}
