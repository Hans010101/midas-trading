'use client'

/**
 * 市场切换条(A 股 / 美股 / 加密)· 全站共用组件。
 *
 * 从工作台 Header 抽出 · 工作台页 + 加密市场列表页共用同一份。
 *
 * 行为(按当前所在页面自适应,组件自己判断「当前在哪个市场」):
 *  - 在工作台(/workbench):
 *      · A 股 / 美股 → setMarket 工作台内切换(**与抽取前完全一致**,无路由跳转)
 *      · 加密       → 跳 /crypto-market 列表页(B 方案:加密频道 = 列表→详情,
 *                     不再用旧加密工作台;这是相对抽取前唯一的行为变化)
 *      · 选中态     = 工作台 store 的当前 market
 *  - 在加密市场列表页(/crypto-market):
 *      · 加密       → 已在本页,no-op(高亮)
 *      · A 股 / 美股 → setMarket 预设市场 + 跳 /workbench
 *      · 选中态     = 加密
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

  const onCryptoMarket = pathname?.startsWith('/crypto-market') ?? false
  const active: Market = onCryptoMarket ? 'crypto' : storeMarket

  function handleSelect(m: Market) {
    if (m === 'crypto') {
      // 加密统一进列表页;已在列表页则 no-op
      if (!onCryptoMarket) router.push('/crypto-market')
      return
    }
    // A 股 / 美股:setMarket 与抽取前工作台行为完全一致(含再次点击当前市场重置 symbol)
    setMarket(m)
    // 若当前在加密列表页,切 A 股/美股需跳回工作台
    if (onCryptoMarket) router.push('/workbench')
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
