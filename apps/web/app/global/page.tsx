'use client'

/**
 * 全球指标概览页(ADR 0035 阶段 A · /global · 设为市场默认落地页)。
 *
 * 响应式卡片网格(宽窄屏都能用)· 按分类分组(环球指数 / 商品 / 外汇 / 债券 / 加密)。
 * 阶段 B 再叠「世界地图」视觉增强(读同一份数据 · 宽屏地图+列表 / 窄屏卡片)· 不阻塞本基座。
 * 红线:纯只读展示 · 不涉及交易(市场是地区码非交易市场 · 不可下单)。
 */

import { useQuery } from '@tanstack/react-query'
import dynamic from 'next/dynamic'
import { useMemo } from 'react'

import { TopNav } from '@/components/layout/top-nav'
import { QuoteCard } from '@/components/market-home/index-card'
import type { MapQuote } from '@/components/market-home/world-map'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { fetchGlobalOverview } from '@/lib/api/overview'

// 阶段 B 世界地图 · 纯前端视觉增强 · ssr:false 懒加载(含 ~34KB 点阵数据,不进首屏 SSR)
const WorldMap = dynamic(
  () => import('@/components/market-home/world-map').then((m) => m.WorldMap),
  { ssr: false, loading: () => <div className="h-[160px] md:h-[300px]" /> },
)

export default function GlobalOverviewPage() {
  const q = useQuery({
    queryKey: ['global-overview'],
    queryFn: ({ signal }) => fetchGlobalOverview(signal),
    retry: 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const groups = q.data?.groups ?? []

  // 世界地图读同一份数据:symbol → {名称, 涨跌幅}(地图按 symbol 取主要股指)
  // 依赖 q.data(TanStack 稳定引用)· 不依赖每渲染都新建的 groups 数组
  const quoteMap = useMemo(() => {
    const m = new Map<string, MapQuote>()
    for (const group of q.data?.groups ?? []) {
      for (const it of group.items) m.set(it.symbol, { name: it.name, changePct: it.change_pct })
    }
    return m
  }, [q.data])

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />

      <main className="flex-1">
        <div className="mx-auto max-w-[1600px] px-6 py-5">
          {q.isPending && <LoadingNote className="py-10" />}
          {q.isError && <EmptyState title="暂时无法读取行情" hint="后端不可达 · 稍后自动重试" />}
          {q.isSuccess && groups.length === 0 && (
            <EmptyState title="全球指标数据待采集" hint="采集任务每 10 分钟写入快照" />
          )}

          {/* 阶段 B · 世界地图视觉(整条在卡片网格上方 · 读同一份数据 · 上下布局宽窄屏一致) */}
          {groups.length > 0 && (
            <div className="mb-6 md:mb-8">
              <div className="mx-auto max-w-[1200px]">
                <WorldMap quotes={quoteMap} />
              </div>
            </div>
          )}

          {groups.map((group) => (
            <section key={group.category} className="mb-6">
              <h2 className="mb-3 font-serif text-sm font-bold text-foreground">{group.label}</h2>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                {group.items.map((it) => (
                  <QuoteCard
                    key={it.symbol}
                    name={it.name}
                    lastPoint={it.last_point}
                    changePoint={it.change_point}
                    changePct={it.change_pct}
                    unit={it.unit}
                  />
                ))}
              </div>
            </section>
          ))}

          <p className="mt-4 text-[11px] text-muted-foreground/60">
            全球核心市场指标 · 数据先采集进库再展示(~15min 延迟)
          </p>
        </div>
      </main>
    </div>
  )
}
