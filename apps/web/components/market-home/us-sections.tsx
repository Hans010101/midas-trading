'use client'

/**
 * 美股榜单区(0023 阶段③ · 3.3)· 仅 /us-market 渲染 · 接 /api/v1/us/board。
 *
 * 决策⑥:策展池(重点关注池 · 非全市场)· 顶部诚实标注。
 * 三块:重点关注池 涨幅/跌幅/成交额 3 榜单 Tab + 行业板块 + 中概股板块(板块表里高亮)。
 * 用 0022 阶段② 共用组件。成交额为美元估(close×volume)· 盘前盘后异动本期不做。
 * 个股详情页 3.4 上线(本期行不可点)· 红线:只读行情 · 仅供参考,不构成投资建议。
 */

import { useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { DataTable, TCell, TH, THead, TRow } from '@/components/ui/data-table'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { fetchUsBoard, type UsSpotRow } from '@/lib/api/us-market'
import { cn } from '@/lib/utils'

type Tab = 'gainers' | 'losers' | 'amount'
const TABS: { key: Tab; label: string }[] = [
  { key: 'gainers', label: '涨幅榜' },
  { key: 'losers', label: '跌幅榜' },
  { key: 'amount', label: '成交额榜' },
]

function fmtPct(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}
function fmtPrice(n: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtUsd(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}
const upDown = (n: number) => (n >= 0 ? 'text-up' : 'text-down')

export function UsSections() {
  const q = useQuery({
    queryKey: ['us-board'],
    queryFn: ({ signal }) => fetchUsBoard(signal),
    retry: 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const [tab, setTab] = useState<Tab>('gainers')

  const poolSize = q.data?.pool_size ?? 0
  const rows: UsSpotRow[] =
    tab === 'gainers'
      ? (q.data?.gainers ?? [])
      : tab === 'losers'
        ? (q.data?.losers ?? [])
        : (q.data?.top_amount ?? [])
  const sectors = q.data?.sectors ?? []

  return (
    <div className="mt-8 space-y-6">
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-serif text-sm font-bold text-foreground">热门美股 · 重点关注池</h2>
          {poolSize > 0 && (
            <span className="text-xs text-muted-foreground/70">池内 {poolSize} 只 · 策展非全市场</span>
          )}
        </div>
        {q.isPending && <LoadingNote className="py-6" />}
        {q.isError && <EmptyState title="暂时无法读取榜单" hint="后端不可达 · 稍后自动重试" />}
        {q.isSuccess && poolSize === 0 && (
          <EmptyState title="榜单数据待采集" hint="美股交易时段自动采集(每 5 分钟)" />
        )}

        {q.isSuccess && poolSize > 0 && (
          <>
            <div className="mb-3 flex overflow-hidden rounded-md border border-paper text-sm">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTab(t.key)}
                  className={cn(
                    'px-4 py-1.5 transition-colors',
                    tab === t.key
                      ? 'bg-midas-red text-white'
                      : 'text-muted-foreground hover:bg-midas-red-glow/50',
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <DataTable minWidth="640px">
              <THead>
                <TH align="center">#</TH>
                <TH>代码</TH>
                <TH>名称</TH>
                <TH>板块</TH>
                <TH align="right">最新价</TH>
                <TH align="right">涨跌幅</TH>
                <TH align="right">成交额</TH>
              </THead>
              <tbody>
                {rows.map((r, i) => (
                  <TRow key={r.symbol}>
                    <TCell align="center" mono className="text-xs text-muted-foreground/70">
                      {i + 1}
                    </TCell>
                    <TCell mono>{r.symbol}</TCell>
                    <TCell className="font-medium text-foreground">{r.name}</TCell>
                    <TCell className="text-xs text-muted-foreground/70">{r.sector}</TCell>
                    <TCell align="right" mono>
                      ${fmtPrice(r.last_price)}
                    </TCell>
                    <TCell align="right" mono className={upDown(r.change_pct)}>
                      {fmtPct(r.change_pct)}
                    </TCell>
                    <TCell align="right" mono className="text-muted-foreground/80">
                      {fmtUsd(r.amount)}
                    </TCell>
                  </TRow>
                ))}
              </tbody>
            </DataTable>
            <p className="mt-2 text-[11px] text-muted-foreground/60">
              重点关注池排行(非全市场)· 成交额为美元估(现价 × 成交量)· 个股详情页 3.4 上线 ·
              仅供参考,不构成投资建议
            </p>
          </>
        )}
      </section>

      {/* 行业板块 + 中概股板块(中概股高亮)*/}
      {q.isSuccess && sectors.length > 0 && (
        <section>
          <h2 className="mb-3 font-serif text-sm font-bold text-foreground">行业板块 · 中概股板块</h2>
          <DataTable minWidth="560px">
            <THead>
              <TH>板块</TH>
              <TH align="right">涨跌幅</TH>
              <TH align="right">池内家数</TH>
              <TH align="right">成交额</TH>
            </THead>
            <tbody>
              {sectors.map((s) => (
                <TRow key={s.name} className={s.name === '中概股' ? 'bg-gold/10' : undefined}>
                  <TCell className="font-medium text-foreground">
                    {s.name}
                    {s.name === '中概股' && (
                      <span className="ml-1 text-[10px] text-gold">中概股板块</span>
                    )}
                  </TCell>
                  <TCell align="right" mono className={upDown(s.change_pct)}>
                    {fmtPct(s.change_pct)}
                  </TCell>
                  <TCell align="right" mono className="text-muted-foreground/80">
                    {s.stock_count}
                  </TCell>
                  <TCell align="right" mono className="text-muted-foreground/80">
                    {fmtUsd(s.total_amount)}
                  </TCell>
                </TRow>
              ))}
            </tbody>
          </DataTable>
          <p className="mt-2 text-[11px] text-muted-foreground/60">
            板块涨跌幅 = 池内成分等权均值 · 中概股板块为策展中概股集合
          </p>
        </section>
      )}
    </div>
  )
}
