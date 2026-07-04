'use client'

/**
 * 持仓与订单 · 四 tab 装配(用户中心模块② · 重组刀3)。
 *
 * tab 用 URL ?tab= 驱动(刷新/分享不丢 · 刀4 改旧链接可精确指 tab):
 *   当前持仓 = 现货节 + 合约节 上下排(字段差异大不混表 · P2 确认口径)
 *   历史持仓 = 现货历史 + 合约历史;订单流水 = 现货流水 + 合约流水(含资金费记录);
 *   条件单 = 全市场全量列表(自包含组件搬入)。
 * 🔴 三条操作链(spot 平仓 / perp 平仓 / 撤条件单)随各自组件整体迁移,链路零改动。
 */

import { useSearchParams } from 'next/navigation'

import { usePathname, useRouter } from '@/i18n/navigation' // ★i18n:locale 感知(useSearchParams 与 locale 无关·留 next/navigation)

import { PerpActivePositions } from '@/components/account/perp-active-positions'
import { PerpClosedPositions } from '@/components/account/perp-closed-positions'
import { PerpOrders } from '@/components/account/perp-orders'
import { SpotClosedPositions } from '@/components/account/spot-closed-positions'
import { SpotOrders } from '@/components/account/spot-orders'
import { SpotPositionsSection } from '@/components/account/spot-positions-section'
import { ConditionalOrdersList } from '@/components/trading/conditional-orders-list'
import { POSITIONS_TABS, normalizePositionsTab } from '@/lib/account-nav'
import { cn } from '@/lib/utils'

export function PositionsHub() {
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const router = useRouter()
  const tab = normalizePositionsTab(searchParams.get('tab'))

  function switchTab(key: string) {
    // replace 不堆历史(tab 切换非页面跳转语义)
    router.replace(key === 'positions' ? pathname : `${pathname}?tab=${key}`)
  }

  return (
    <div>
      <h1 className="mb-4 font-serif text-2xl font-bold text-foreground">持仓与订单</h1>

      {/* 四 tab(framed-segment 范式 · 窄屏可横滚) */}
      <div className="mb-6 overflow-x-auto">
        <div className="flex w-max overflow-hidden rounded-md border border-paper text-sm">
          {POSITIONS_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => switchTab(t.key)}
              className={cn(
                'whitespace-nowrap px-4 py-1.5 transition-colors',
                tab === t.key
                  ? 'bg-midas-red text-white'
                  : 'text-muted-foreground hover:bg-midas-red-glow/50',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'positions' && (
        <div>
          <h2 className="mb-2 font-serif text-base font-bold text-foreground">现货持仓</h2>
          <SpotPositionsSection />
          <h2 className="mb-2 mt-8 font-serif text-base font-bold text-foreground">合约持仓(永续)</h2>
          <PerpActivePositions />
        </div>
      )}

      {tab === 'history' && (
        <div>
          <SpotClosedPositions />
          <PerpClosedPositions />
        </div>
      )}

      {tab === 'orders' && (
        <div>
          <SpotOrders />
          <PerpOrders />
        </div>
      )}

      {tab === 'conditional' && <ConditionalOrdersList />}
    </div>
  )
}
