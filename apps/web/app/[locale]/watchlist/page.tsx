/**
 * 自选汇总页 · /watchlist(0023 阶段③ · 3.6)。
 *
 * 跨市场(A股/美股/加密)自选标的汇总到一个界面 · 复用 0007 watchlist 接口 + 报价 hook。
 * 导航结构跟三市场首页统一(顶栏 TopNav 内含市场 Tab · 第四 Tab「自选」高亮本页)。
 * 未登录由 WatchlistOverview 内引导登录(本路由不在 middleware 保护列表,匿名可达)。
 *
 * 红线:只读行情 · 全程虚拟资金。
 */

import { TopNav } from '@/components/layout/top-nav'
import { WatchlistOverview } from '@/components/watchlist/watchlist-overview'

export default function WatchlistPage() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-[1600px] px-6 py-5">
          <WatchlistOverview />
        </div>
      </main>
    </div>
  )
}
