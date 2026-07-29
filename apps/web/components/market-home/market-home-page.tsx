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
import Link from 'next/link'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { TopNav } from '@/components/layout/top-nav'
import { CnSections } from '@/components/market-home/cn-sections'
import { HkSections } from '@/components/market-home/hk-sections'
import { QuoteCard } from '@/components/market-home/index-card'
import { UsSections } from '@/components/market-home/us-sections'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { useRuntimeDocumentTitle } from '@/hooks/use-runtime-document-title'
import { fetchMarketOverview, type MarketKind } from '@/lib/api/market-home'

export function MarketHomePage({ market }: { market: MarketKind }) {
  const { locale } = useRuntimeLocale()
  const title = market === 'cn'
    ? { en: 'A-shares', zh: 'A 股行情' }
    : market === 'us'
      ? { en: 'U.S. Stocks', zh: '美股行情' }
      : { en: 'Hong Kong Stocks', zh: '港股行情' }
  useRuntimeDocumentTitle({
    locale,
    english: title.en,
    chinese: title.zh,
  })
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
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-serif text-sm font-bold text-foreground">
              {locale === 'en' ? 'Market indices' : '大盘指数'}
            </h2>
            {/* 选股入口 · ★MarketKind 类型仅 cn/us/hk(加密是独立页面 crypto-market·不走本组件)→
                此入口【类型层面】只在股票市场出现,加密天然不含。筛选器第一版只做股票。 */}
            <Link
              href="/screener"
              className="inline-flex items-center gap-1 rounded-md border border-midas-red/40 bg-midas-red/[0.06] px-3 py-1 text-xs font-medium text-midas-red transition-colors hover:bg-midas-red/[0.12]"
            >
              {locale === 'en' ? 'Stock screener →' : '选股筛选器 →'}
            </Link>
          </div>
          {q.isPending && <LoadingNote className="py-10" />}
          {q.isError && (
            <EmptyState
              title={locale === 'en' ? 'Market data is temporarily unavailable' : '暂时无法读取行情'}
              hint={locale === 'en' ? 'The data service will retry automatically' : '后端不可达 · 稍后自动重试'}
            />
          )}
          {q.isSuccess && indices.length === 0 && (
            <EmptyState
              title={locale === 'en' ? 'Index data is awaiting collection' : '指数数据待采集'}
              hint={
                locale === 'en'
                  ? 'The collection job records snapshots during market hours'
                  : '采集任务将在交易时段写入快照'
              }
            />
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
        </div>
      </main>
    </div>
  )
}

// IndexCard 已抽到 components/market-home/index-card.tsx 的 QuoteCard(共用 · 单位感知)。
