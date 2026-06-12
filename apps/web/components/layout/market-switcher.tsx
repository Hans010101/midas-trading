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
import { detailMarketOf, homeMarketOf, resolveActiveMarket } from '@/lib/market-nav'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

// 顶部导航的市场【显示次序】(加密前移 · 功能最全)· 本地常量纯渲染序:
// ⛔ 不动 shared MARKETS(它还被 wallet-section 列序 + 后端校验引用,改了有隐性波及);
// handleSelect / active 按 market 值工作,与渲染顺序无关。
const NAV_MARKETS: readonly Market[] = ['crypto', 'us', 'cn', 'hk']

export function MarketSwitcher({ className }: { className?: string }) {
  const pathname = usePathname()
  const router = useRouter()
  const storeMarket = useWorkbenchStore((s) => s.market)
  const setMarket = useWorkbenchStore((s) => s.setMarket)

  // 市场路由判定收敛进 lib/market-nav(纯函数 · vitest 钉死)——
  // 修复刀:原 active 链 `home ?? detail ?? storeMarket` 让 /account 等中性页
  // 回退 store 残留值误亮"加密";逐页豁免(global/watchlist/lab)是反模式。
  // 现反转白名单:store 兜底只在 /workbench 生效,其余非市场路径全不亮。
  const homeMarket = homeMarketOf(pathname)
  const detailMarket = detailMarketOf(pathname)
  const onGlobal = pathname?.startsWith('/global') ?? false
  // 自选汇总页(3.6)· 末位 Tab · 非市场,单独高亮
  const onWatchlist = pathname === '/watchlist'
  // 策略研究室(P1-4d)· 非市场 · /lab 与 /lab/report 都算 · 单独高亮
  const onLab = pathname?.startsWith('/lab') ?? false
  const active = resolveActiveMarket(pathname, storeMarket)

  function handleSelect(m: Market) {
    // 港股(hk)阶段二单元3:行情页(/hk-market 策展池 18 只列表)已上线 →
    // 点 hk Tab 统一进行情页(与 cn/us/crypto 一致:Tab → 市场首页 → 点标的进详情)。
    // 港股只读 · 不进工作台 K 线流(拍板③ workbench 不接 hk)。
    if (m === 'hk') {
      router.push('/hk-market')
      return
    }
    // 在任一市场首页 / 详情页(*-preview)/ 全球概览:点市场 → 跳对应市场首页(已在本页则 no-op)
    if (homeMarket || detailMarket || onGlobal) {
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
      <button
        type="button"
        onClick={() => router.push('/global')}
        className={cn(
          'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
          onGlobal
            ? 'bg-midas-red text-primary-foreground'
            : 'text-muted-foreground hover:bg-midas-red-glow hover:text-foreground',
        )}
      >
        全球市场
      </button>
      {NAV_MARKETS.map((m) => (
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
      <span className="mx-1 h-4 w-px self-center bg-paper" aria-hidden />
      <button
        type="button"
        onClick={() => router.push('/watchlist')}
        className={cn(
          'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
          onWatchlist
            ? 'bg-midas-red text-primary-foreground'
            : 'text-muted-foreground hover:bg-midas-red-glow hover:text-foreground',
        )}
      >
        自选
      </button>
      <button
        type="button"
        // 方案乙:研究室默认落 AI 沙盘助手(/lab 回测 URL 不动不破书签)
        onClick={() => router.push('/lab/assistant')}
        className={cn(
          'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
          onLab
            ? 'bg-midas-red text-primary-foreground'
            : 'text-muted-foreground hover:bg-midas-red-glow hover:text-foreground',
        )}
      >
        策略研究室
      </button>
    </nav>
  )
}
