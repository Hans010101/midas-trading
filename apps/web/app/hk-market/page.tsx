'use client'

/**
 * 港股行情页 · /hk-market(港股阶段二 单元3)· 策展池 18 只简化列表。
 *
 * 拍板①:简化列表(代码+名称+板块+最新价+日涨跌 → 点行进详情)· 全榜单 MarketHomePage 留阶段四。
 * 每行复用 useKline(hk,1d,limit=2)算最新价 + 日涨跌(港股只日线 · 同详情页 Header 取价方式 → queryKey 命中复用)。
 * 点行 → /hk-preview?symbol&name(K线+缠论)。
 * ★ 港股只读:行情展示 · 不下单不接 AI(同详情页边界 · 拍板②④)。
 * 红线:仅虚拟资金。
 */

import { useRouter } from 'next/navigation'

import { MarketSwitcher } from '@/components/layout/market-switcher'
import { TopNav } from '@/components/layout/top-nav'
import { useKline } from '@/hooks/use-kline'
import { HK_POOL, type HkPoolItem } from '@/lib/hk-pool'
import { cn } from '@/lib/utils'

function fmtHkd(n: number): string {
  return `HK$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function HkMarketPage() {
  const router = useRouter()
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <div className="shrink-0 border-b border-paper bg-background px-6 py-2">
        <MarketSwitcher />
      </div>

      <main className="flex-1">
        <div className="mx-auto max-w-[1100px] px-6 py-6">
          <div className="mb-4 flex flex-wrap items-baseline gap-2">
            <h1 className="font-serif text-xl font-bold">港股 · 精选</h1>
            <span className="text-xs text-muted-foreground/70">
              策展池 {HK_POOL.length} 只 · 点击看 K 线 + 缠论(港股只读 · 不可交易)
            </span>
          </div>

          <div className="overflow-hidden rounded-lg border border-paper bg-surface-card">
            <table className="w-full text-sm">
              <thead className="border-b border-paper bg-cream/50 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">代码 / 名称</th>
                  <th className="px-4 py-2.5 text-left font-medium">板块</th>
                  <th className="px-4 py-2.5 text-right font-medium">最新价</th>
                  <th className="px-4 py-2.5 text-right font-medium">日涨跌</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {HK_POOL.map((it) => (
                  <HkRow
                    key={it.symbol}
                    item={it}
                    onClick={() =>
                      router.push(`/hk-preview?symbol=${it.symbol}&name=${encodeURIComponent(it.name)}`)
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-3 text-[11px] text-muted-foreground/60">
            港股策展池(蓝筹 + 科技 + 中概回港)· 最新价 / 日涨跌 = 日 K 末根真实(港股只日线)·
            点行进详情页看 K线 + 缠论 · 港股只读、不下单不接 AI
          </p>
        </div>
      </main>
    </div>
  )
}

function HkRow({ item, onClick }: { item: HkPoolItem; onClick: () => void }) {
  // 日 K 末两根算最新价 + 日涨跌(港股只日线)· queryKey 与详情页 Header 同 → 点进详情命中缓存
  const { data, isPending, isError } = useKline({
    symbol: item.symbol,
    market: 'hk',
    period: '1d',
    limit: 2,
  })
  const items = data?.items ?? []
  const last = items.at(-1)
  const prev = items.at(-2)
  const price = last?.close ?? null
  const chgPct =
    last && prev && prev.close !== 0 ? ((last.close - prev.close) / prev.close) * 100 : null
  const up = chgPct !== null && chgPct >= 0

  return (
    <tr
      onClick={onClick}
      title="点击打开港股详情页(K线 + 缠论)"
      className="group cursor-pointer border-b border-paper/60 transition-colors hover:bg-midas-red-glow/30"
    >
      <td className="px-4 py-3">
        <span className="font-serif font-bold text-foreground">{item.symbol}</span>
        <span className="ml-2 text-xs text-muted-foreground">{item.name}</span>
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground/70">{item.sector}</td>
      <td className="px-4 py-3 text-right font-mono tabular-nums">
        {isPending ? '…' : isError || price === null ? '—' : fmtHkd(price)}
      </td>
      <td
        className={cn(
          'px-4 py-3 text-right font-mono tabular-nums',
          chgPct === null ? 'text-muted-foreground/40' : up ? 'text-up' : 'text-down',
        )}
      >
        {chgPct === null ? '—' : `${up ? '+' : ''}${chgPct.toFixed(2)}%`}
      </td>
      <td className="px-2 text-center text-muted-foreground/30 transition-colors group-hover:text-midas-red">
        ›
      </td>
    </tr>
  )
}
