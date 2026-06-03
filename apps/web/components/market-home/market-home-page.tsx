'use client'

/**
 * A股 / 美股 / 港股 市场首页骨架(0023 阶段③)· cn / us / hk 共用同一份。
 *
 * 大盘指数卡(4 张)+ 各市场榜单 sections。数据走只读端点 /api/v1/{cn|us|hk}/overview。
 * 红线:大盘指数为真实行情快照(只读)· 非交易时段为最新收盘快照。
 *
 * 2026-06 顶栏重构:市场 Tab 上移到全站 TopNav(去掉本页独立 MarketSwitcher 行)·
 * 去掉「{市场}市场 盘中 截至」状态条(原 StatusBanner · 无实质信息价值 · status 数据不再展示)。
 */

import { useQuery } from '@tanstack/react-query'

import { TopNav } from '@/components/layout/top-nav'
import { CnSections } from '@/components/market-home/cn-sections'
import { HkSections } from '@/components/market-home/hk-sections'
import { QuoteCard } from '@/components/market-home/index-card'
import { UsSections } from '@/components/market-home/us-sections'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { fetchMarketOverview, type MarketKind } from '@/lib/api/market-home'

const MARKET_NAME: Record<MarketKind, string> = { cn: 'A 股', us: '美股', hk: '港股' }

export function MarketHomePage({ market }: { market: MarketKind }) {
  const q = useQuery({
    queryKey: ['market-overview', market],
    queryFn: ({ signal }) => fetchMarketOverview(market, signal),
    retry: 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const indices = q.data?.indices ?? []

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />

      <main className="flex-1">
        <div className="mx-auto max-w-[1600px] px-6 py-5">
          <h2 className="mb-3 font-serif text-sm font-bold text-foreground">大盘指数</h2>
          {q.isPending && <LoadingNote className="py-10" />}
          {q.isError && (
            <EmptyState title="暂时无法读取行情" hint="后端不可达 · 稍后自动重试" />
          )}
          {q.isSuccess && indices.length === 0 && (
            <EmptyState title="指数数据待采集" hint="采集任务将在交易时段写入快照" />
          )}
          {q.isSuccess && indices.length > 0 && (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {indices.map((idx) => (
                <QuoteCard
                  key={idx.symbol}
                  name={idx.name}
                  lastPoint={idx.last_point}
                  changePoint={idx.change_point}
                  changePct={idx.change_pct}
                />
              ))}
            </div>
          )}

          {market === 'cn' ? <CnSections /> : market === 'us' ? <UsSections /> : <HkSections />}

          <p className="mt-6 text-[11px] text-muted-foreground/60">
            大盘指数为{MARKET_NAME[market]}实时快照
            {market === 'cn'
              ? '(Sina · 交易时段刷新)'
              : market === 'us'
                ? '(yfinance · ET 含夏令时)'
                : ''}
            · 非交易时段为最新收盘快照
          </p>
        </div>
      </main>
    </div>
  )
}

// IndexCard 已抽到 components/market-home/index-card.tsx 的 QuoteCard(共用 · 单位感知)。
