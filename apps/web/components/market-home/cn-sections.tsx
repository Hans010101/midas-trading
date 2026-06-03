'use client'

/**
 * A股榜单区(0023 阶段③ · 3.2)· 仅 /cn-market 渲染 · 接 /api/v1/cn/board。
 *
 * 三块:市场情绪条(涨跌平家数 + 涨跌停估)+ 3 榜单 Tab(涨幅/跌幅/成交额)+ 行业板块。
 * 用 0022 阶段② 共用组件(Panel / DataTable / EmptyState / LoadingNote)。
 * 换手率/量比本期不渲染(Sina 无字段 · 东财不可达)· 个股详情页 3.4 上线(本期行不可点)。
 * 红线:只读行情。
 */

import { useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { SectorHeatmap } from '@/components/market-home/sector-heatmap'
import { DataTable, TCell, TH, THead, TRow } from '@/components/ui/data-table'
import { Panel } from '@/components/ui/panel'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { fetchCnBoard, type CnBreadth, type CnSpotRow } from '@/lib/api/cn-market'
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
function fmtAmount(n: number): string {
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)}亿`
  if (n >= 1e4) return `${(n / 1e4).toFixed(0)}万`
  return n.toFixed(0)
}
const upDown = (n: number) => (n >= 0 ? 'text-up' : 'text-down')

// 行点击 → 新标签打开 A股个股详情页(纯做多下单)· 同 crypto-market 模式
function openDetail(symbol: string, name: string) {
  window.open(
    `/cn-preview?symbol=${encodeURIComponent(symbol)}&name=${encodeURIComponent(name)}`,
    '_blank',
    'noopener,noreferrer',
  )
}

export function CnSections() {
  const q = useQuery({
    queryKey: ['cn-board'],
    queryFn: ({ signal }) => fetchCnBoard(signal),
    retry: 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const [tab, setTab] = useState<Tab>('gainers')

  const breadth = q.data?.breadth ?? null
  const rows: CnSpotRow[] =
    tab === 'gainers'
      ? (q.data?.gainers ?? [])
      : tab === 'losers'
        ? (q.data?.losers ?? [])
        : (q.data?.top_amount ?? [])
  const sectors = q.data?.sectors ?? []

  return (
    <div className="mt-8 space-y-6">
      {/* 市场情绪条 */}
      <section>
        <h2 className="mb-3 font-serif text-sm font-bold text-foreground">市场情绪</h2>
        {q.isPending && <LoadingNote className="py-6" />}
        {q.isError && <EmptyState title="暂时无法读取榜单" hint="后端不可达 · 稍后自动重试" />}
        {q.isSuccess && !breadth && (
          <EmptyState title="榜单数据待采集" hint="A股交易时段自动采集(每 3 分钟)" />
        )}
        {breadth && <BreadthBar b={breadth} />}
      </section>

      {/* 行业板块热力图(上移到榜单前 · 当市场概览)*/}
      {q.isSuccess && sectors.length > 0 && (
        <section>
          <h2 className="mb-3 font-serif text-sm font-bold text-foreground">行业板块</h2>
          <SectorHeatmap
            sectors={sectors}
            fmtAmount={fmtAmount}
            max={24}
            weightNote="行业涨跌按成交额加权 · 取主要 24 板块(Sina 新浪行业)"
          />
        </section>
      )}

      {/* 榜单 3 Tab */}
      {q.isSuccess && breadth && (
        <section>
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
              <TH align="right">最新价</TH>
              <TH align="right">涨跌幅</TH>
              <TH align="right">成交额</TH>
            </THead>
            <tbody>
              {rows.length === 0 && (
                <TRow>
                  <TCell align="center" className="py-8 text-muted-foreground/60" colSpan={6}>
                    暂无数据
                  </TCell>
                </TRow>
              )}
              {rows.map((r, i) => (
                <TRow
                  key={r.symbol}
                  onClick={() => openDetail(r.symbol, r.name)}
                  className="cursor-pointer transition-colors hover:bg-midas-red-glow/30"
                  title="点击查看详情 · 下单"
                >
                  <TCell align="center" mono className="text-xs text-muted-foreground/70">
                    {i + 1}
                  </TCell>
                  <TCell mono>{r.symbol}</TCell>
                  <TCell className="font-medium text-foreground">{r.name}</TCell>
                  <TCell align="right" mono>
                    {fmtPrice(r.last_price)}
                  </TCell>
                  <TCell align="right" mono className={upDown(r.change_pct)}>
                    {fmtPct(r.change_pct)}
                  </TCell>
                  <TCell align="right" mono className="text-muted-foreground/80">
                    {fmtAmount(r.amount)}
                  </TCell>
                </TRow>
              ))}
            </tbody>
          </DataTable>
          <p className="mt-2 text-[11px] text-muted-foreground/60">
            点击个股看详情 / 下单 · 数据 Sina 实时快照
          </p>
        </section>
      )}

    </div>
  )
}

function BreadthBar({ b }: { b: CnBreadth }) {
  const total = b.up_count + b.down_count + b.flat_count || 1
  const upPct = (b.up_count / total) * 100
  const flatPct = (b.flat_count / total) * 100
  const downPct = (b.down_count / total) * 100
  return (
    <Panel padding="md">
      <div className="flex items-center justify-between font-mono text-sm">
        <span className="font-bold text-up">{b.up_count} 涨</span>
        <span className="text-muted-foreground">{b.flat_count} 平</span>
        <span className="font-bold text-down">{b.down_count} 跌</span>
      </div>
      <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-paper">
        <div className="bg-up" style={{ width: `${upPct}%` }} />
        <div className="bg-muted/50" style={{ width: `${flatPct}%` }} />
        <div className="bg-down" style={{ width: `${downPct}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>
          涨停 <b className="font-mono text-up">{b.limit_up_count}</b> · 跌停{' '}
          <b className="font-mono text-down">{b.limit_down_count}</b>
          <span className="ml-1 text-muted-foreground/50">(按涨跌幅阈值估算)</span>
        </span>
        <span>
          两市成交额 <b className="font-mono text-foreground">{fmtAmount(b.total_amount)}</b>
        </span>
      </div>
    </Panel>
  )
}
