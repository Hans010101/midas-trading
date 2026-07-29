/**
 * 自选汇总页 · /watchlist(0023 阶段③ · 3.6)。
 *
 * 跨市场(A股/美股/加密)自选标的汇总到一个界面 · 复用 0007 watchlist 接口 + 报价 hook。
 * 导航结构跟三市场首页统一(顶栏 TopNav 内含市场 Tab · 第四 Tab「自选」高亮本页)。
 * 未登录由 WatchlistOverview 内引导登录(本路由不在 middleware 保护列表,匿名可达)。
 *
 * 红线:只读行情 · 全程虚拟资金。
 */

import type { Metadata } from 'next'
import { cookies } from 'next/headers'

import { TopNav } from '@/components/layout/top-nav'
import { WatchlistOverview } from '@/components/watchlist/watchlist-overview'
import { LOCALE_COOKIE } from '@/i18n/routing'

// SEO 批3:自选页独立 metadata(server 页 · 直接 export)。
export async function generateMetadata(): Promise<Metadata> {
  const english = (await cookies()).get(LOCALE_COOKIE)?.value === 'en'
  return {
    title: {
      absolute: english ? 'Watchlist · Midas Trading' : '自选汇总 · 点金 Midas',
    },
    description: english
      ? 'Track A-shares, U.S. stocks, Hong Kong stocks and crypto instruments in one cross-market watchlist.'
      : '跨市场自选标的汇总:加密、美股、A股、港股自选行情一屏查看。',
    alternates: { canonical: '/watchlist' },
  }
}

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
