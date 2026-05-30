'use client'

/**
 * A股 / 美股 市场首页骨架(0023 阶段③ · 3.1 基建)· cn / us 共用同一份。
 *
 * 借用加密列表页架构 + 0022 阶段② 共用组件库(Panel / StatusPill / EmptyState / LoadingNote)。
 * 3.1 内容:顶部市场切换 + 市场状态条(交易时段)+ 大盘指数卡(4 张)+ 榜单占位(3.2 / 3.3)。
 *
 * 数据走只读端点 /api/v1/{cn|us}/overview(lib/api/market-home.ts)。
 * 红线:大盘指数为真实行情快照(只读)· 非交易时段为最新收盘快照 · 仅供参考,不构成投资建议。
 */

import { useQuery } from '@tanstack/react-query'

import { MarketSwitcher } from '@/components/layout/market-switcher'
import { TopNav } from '@/components/layout/top-nav'
import { CnSections } from '@/components/market-home/cn-sections'
import { QuoteCard } from '@/components/market-home/index-card'
import { UsSections } from '@/components/market-home/us-sections'
import { StatusPill } from '@/components/ui/direction-badge'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import {
  fetchMarketOverview,
  type MarketKind,
  type MarketStatusCode,
  type MarketStatusInfo,
} from '@/lib/api/market-home'

const MARKET_NAME: Record<MarketKind, string> = { cn: 'A 股', us: '美股' }

const STATUS_TONE: Record<MarketStatusCode, 'success' | 'warn' | 'muted' | 'neutral'> = {
  open: 'success',
  pre_market: 'warn',
  post_market: 'warn',
  closed: 'muted',
  closed_holiday: 'neutral',
}

function fmtTime(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

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
      <div className="shrink-0 border-b border-paper bg-background px-6 py-2">
        <MarketSwitcher />
      </div>

      <main className="flex-1">
        <StatusBanner market={market} status={q.data?.status} loading={q.isPending} />

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

          {market === 'cn' ? <CnSections /> : <UsSections />}

          <p className="mt-6 text-[11px] text-muted-foreground/60">
            大盘指数为{MARKET_NAME[market]}实时快照(
            {market === 'cn' ? 'Sina · 交易时段刷新' : 'yfinance · ET 含夏令时'})· 非交易时段为最新收盘快照 ·
            仅供参考,不构成投资建议
          </p>
        </div>
      </main>
    </div>
  )
}

function StatusBanner({
  market,
  status,
  loading,
}: {
  market: MarketKind
  status?: MarketStatusInfo
  loading: boolean
}) {
  const tone = status ? STATUS_TONE[status.status] : 'muted'
  const label = loading ? '载入中…' : (status?.label ?? '—')
  const dataAt = status?.data_as_of ? fmtTime(status.data_as_of) : ''
  return (
    <div className="flex items-center justify-center gap-2 border-b border-dashed border-gold/60 bg-gold/10 px-6 py-2 text-center text-xs text-gold">
      <span className="font-bold">{MARKET_NAME[market]}市场</span>
      <StatusPill tone={tone}>{label}</StatusPill>
      {dataAt && <span className="text-muted-foreground/70">截至 {dataAt}</span>}
    </div>
  )
}

// IndexCard 已抽到 components/market-home/index-card.tsx 的 QuoteCard(共用 · 单位感知)。
