'use client'

/**
 * 港股榜单区(港股首页全市场)· 仅 /hk-market 渲染 · 接 /api/v1/hk/board。
 *
 * ★★ 标注「主要成分股 / 活跃精选」· 【绝不写"全市场"】:数据 = 新浪限页 ~900 只主要成分(非 2764 全市场)·
 *    同美股「策展非全市场」· 诚实不假装全市场。
 * 两块:情绪条(涨跌平家数 + 总成交额 · ★港股无涨跌停 · 对比 cn 去掉涨跌停行)+ 3 榜单 Tab(涨幅/跌幅/成交额)。
 * 板块暂不做(港股全市场无现成行业源 · 留后续)。行点击 → /hk-preview 详情页(K线+缠论)。
 * 红线:只读行情 · 港股不下单不接 AI(阶段三)。
 */

import { useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { DataTable, TCell, TH, THead, TRow } from '@/components/ui/data-table'
import { Panel } from '@/components/ui/panel'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { fetchHkBoard, type HkBreadth, type HkSpotRow } from '@/lib/api/hk-market'
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

// 行点击 → 新标签打开港股详情页(K线+缠论 · 只读 · 不下单)
function openDetail(symbol: string, name: string) {
  window.open(
    `/hk-preview?symbol=${encodeURIComponent(symbol)}&name=${encodeURIComponent(name)}`,
    '_blank',
    'noopener,noreferrer',
  )
}

export function HkSections() {
  const q = useQuery({
    queryKey: ['hk-board'],
    queryFn: ({ signal }) => fetchHkBoard(signal),
    retry: 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const [tab, setTab] = useState<Tab>('gainers')

  const breadth = q.data?.breadth ?? null
  const rows: HkSpotRow[] =
    tab === 'gainers'
      ? (q.data?.gainers ?? [])
      : tab === 'losers'
        ? (q.data?.losers ?? [])
        : (q.data?.top_amount ?? [])

  return (
    <div className="mt-8 space-y-6">
      {/* 市场情绪条 · ★标注主要成分股(非全市场) */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-serif text-sm font-bold text-foreground">市场情绪 · 主要成分股</h2>
          <span className="text-xs text-muted-foreground/70">活跃精选 ~900 只 · 非全市场</span>
        </div>
        {q.isPending && <LoadingNote className="py-6" />}
        {q.isError && <EmptyState title="暂时无法读取榜单" hint="后端不可达 · 稍后自动重试" />}
        {q.isSuccess && !breadth && (
          <EmptyState title="榜单数据待采集" hint="港股交易时段自动采集(每 3 分钟)" />
        )}
        {breadth && <BreadthBar b={breadth} />}
      </section>

      {/* 榜单 3 Tab(同一份主要成分股快照 3 种排序) */}
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
                  title="点击查看详情(K线 + 缠论)"
                >
                  <TCell align="center" mono className="text-xs text-muted-foreground/70">
                    {i + 1}
                  </TCell>
                  <TCell mono>{r.symbol}</TCell>
                  <TCell className="font-medium text-foreground">{r.name}</TCell>
                  <TCell align="right" mono>
                    HK${fmtPrice(r.last_price)}
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
            ★ 主要成分股 / 活跃精选(新浪源 ~900 只 · 非全市场 2764)· 点击个股看 K线 + 缠论 · 港股只读不下单
          </p>
        </section>
      )}
    </div>
  )
}

function BreadthBar({ b }: { b: HkBreadth }) {
  const total = b.up_count + b.down_count + b.flat_count || 1
  const upPct = (b.up_count / total) * 100
  const flatPct = (b.flat_count / total) * 100
  const downPct = (b.down_count / total) * 100
  const fmtAmt = (n: number) =>
    n >= 1e8 ? `${(n / 1e8).toFixed(0)}亿` : `${(n / 1e4).toFixed(0)}万`
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
          主要成分股成交额 <b className="font-mono text-foreground">HK${fmtAmt(b.total_amount)}</b>
        </span>
        <span className="text-muted-foreground/50">(港股无涨跌停制度 · 涨跌家数基于 ~900 只主要成分)</span>
      </div>
    </Panel>
  )
}
