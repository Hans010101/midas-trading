/**
 * 港股市场首页占位(阶段一 P1-2)· /hk-market。
 *
 * 让 UI「认识」港股市场:市场切换器有「港股」Tab,点进来到这。
 * ★ 港股数据未上线(CH 迁移 + P1-3 采集之前)→ 纯 coming-soon 占位,不请求任何接口
 *   (避免触达未含 hk 的后端数据层)。阶段四再做榜单首页(同 /cn-market、/us-market)。
 * 红线:仅虚拟资金。
 */

import { MarketSwitcher } from '@/components/layout/market-switcher'
import { TopNav } from '@/components/layout/top-nav'
import { EmptyState } from '@/components/ui/state'

export default function HkMarketPage() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <div className="shrink-0 border-b border-paper bg-background px-6 py-2">
        <MarketSwitcher />
      </div>

      <main className="flex-1">
        <div className="flex items-center justify-center gap-2 border-b border-dashed border-gold/60 bg-gold/10 px-6 py-2 text-center text-xs text-gold">
          <span className="font-bold">港股市场</span>
          <span className="text-muted-foreground/70">即将上线</span>
        </div>

        <div className="mx-auto max-w-[1600px] px-6 py-16">
          <EmptyState
            title="港股即将上线 · 数据采集中"
            hint="正在接入港股行情(腾讯 00700 等热门标的)· 上线后可看 K 线 + 建虚拟单"
          />
        </div>
      </main>
    </div>
  )
}
