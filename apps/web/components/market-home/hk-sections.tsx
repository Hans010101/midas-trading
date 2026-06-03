'use client'

/**
 * 港股榜单区(港股首页全市场)· 仅 /hk-market 渲染 · 接 /api/v1/hk/board(limit=900)。
 *
 * ★★ 标注「主要成分股 / 活跃精选」· 【绝不写"全市场"】(新浪限页 ~900 只 · 非 2764)· 诚实。
 * 三块:情绪条(涨跌平 + 总成交额 · ★港股无涨跌停)+ 工具条(榜单 Tab + 搜索框)+ 榜单(无限滚动到 ~900 只到底)。
 * 搜索 = 本地过滤当前榜单 ~900 只主要成分(代码 / 名称)· 点行 → /hk-preview(K线+缠论)。
 * 行业板块(A2)走独立端点 /hk/sectors(yfinance GICS 行业源 · worker 周采 · 见下方板块区)。
 * 红线:只读 · 港股下单走详情页(阶段三 · 本页不下单)。
 */

import { useEffect, useMemo, useRef, useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { SectorHeatmap } from '@/components/market-home/sector-heatmap'
import { DataTable, TCell, TH, THead, TRow } from '@/components/ui/data-table'
import { Panel } from '@/components/ui/panel'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { fetchHkBoard, fetchHkSectors, type HkBreadth, type HkSpotRow } from '@/lib/api/hk-market'
import { cn } from '@/lib/utils'

const PAGE_STEP = 30 // 无限滚动每次续加载行数(数据池 ~900 只 · 到底为止)

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
    queryFn: ({ signal }) => fetchHkBoard(900, signal), // 取数据池全量 ~900 只 · 供本地搜索 + 滚动
    retry: 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  // 行业板块(独立端点 · yfinance GICS 行业源 · A2)· 不和 board 混 · 频率低些
  const sectorQ = useQuery({
    queryKey: ['hk-sectors'],
    queryFn: ({ signal }) => fetchHkSectors(signal),
    retry: 0,
    staleTime: 60_000,
    refetchInterval: 120_000,
  })
  const [tab, setTab] = useState<Tab>('gainers')
  const [query, setQuery] = useState('')
  const [visibleCount, setVisibleCount] = useState(PAGE_STEP)

  const breadth = q.data?.breadth ?? null
  const sectors = sectorQ.data?.sectors ?? []

  // 当前 tab 全集(~900 只 · 后端已按对应维度排序)
  const fullRows: HkSpotRow[] = useMemo(() => {
    if (!q.data) return []
    return tab === 'gainers'
      ? q.data.gainers
      : tab === 'losers'
        ? q.data.losers
        : q.data.top_amount
  }, [q.data, tab])

  // 搜索过滤(本地 · 代码 / 名称 · 范围 = 当前榜单 ~900 只主要成分)
  const viewRows = useMemo(() => {
    const ql = query.trim().toLowerCase()
    if (!ql) return fullRows
    return fullRows.filter(
      (r) => r.symbol.toLowerCase().includes(ql) || r.name.toLowerCase().includes(ql),
    )
  }, [fullRows, query])

  const visibleRows = useMemo(() => viewRows.slice(0, visibleCount), [viewRows, visibleCount])

  // tab / 搜索变 → 重置滚动到首屏
  useEffect(() => {
    setVisibleCount(PAGE_STEP)
  }, [tab, query])

  // 无限滚动:sentinel 进视口 → 续加载(到 viewRows.length = ~900 只到底 · 不假装更多)
  const sentinelRef = useRef<HTMLTableRowElement | null>(null)
  const hasMore = visibleCount < viewRows.length
  useEffect(() => {
    const el = sentinelRef.current
    if (!el || !hasMore) return
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisibleCount((c) => Math.min(c + PAGE_STEP, viewRows.length))
        }
      },
      { rootMargin: '300px' }, // 提前 300px 预加载 · 滚动更顺
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [hasMore, viewRows.length, visibleCount])

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

      {/* 行业板块热力图(上移到榜单前 · 当市场概览 · 独立端点 yfinance GICS)*/}
      {sectorQ.isSuccess && sectors.length > 0 && (
        <section>
          <h2 className="mb-3 font-serif text-sm font-bold text-foreground">行业板块</h2>
          <SectorHeatmap
            sectors={sectors}
            fmtAmount={fmtAmount}
            weightNote="行业 GICS(yfinance)· 成交额加权 · 范围主要成分 ~900 只"
          />
        </section>
      )}

      {/* 工具条(榜单 Tab + 搜索框)+ 榜单(无限滚动到 ~900 只) */}
      {q.isSuccess && breadth && (
        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex overflow-hidden rounded-md border border-paper text-sm">
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
            {/* 搜索框 · 对齐加密首页位置/风格 · 本地过滤主要成分股 */}
            <div className="flex items-center gap-1.5 rounded-md border border-paper bg-surface-card px-3 py-1.5 text-sm">
              <SearchIcon />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索港股(主要成分股)"
                className="w-44 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
              />
            </div>
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
              {viewRows.length === 0 && (
                <TRow>
                  <TCell align="center" className="py-8 text-muted-foreground/60" colSpan={6}>
                    {query ? '无匹配港股' : '暂无数据'}
                  </TCell>
                </TRow>
              )}
              {visibleRows.map((r, i) => (
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
              {/* 无限滚动哨兵 · 进视口续加载 · 到 ~900 只到底自动消失(不假装更多) */}
              {hasMore && (
                <tr ref={sentinelRef}>
                  <td colSpan={6} className="px-3 py-4 text-center text-xs text-muted-foreground/50">
                    下拉加载更多…
                  </td>
                </tr>
              )}
            </tbody>
          </DataTable>
          <p className="mt-2 text-[11px] text-muted-foreground/60">
            ★ 主要成分股 / 活跃精选(~900 只 · 非全市场 2764)· 共 {viewRows.length} 只 ·
            点击看 K线 + 缠论 · 港股只读不下单
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

function SearchIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className="text-muted-foreground/50"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  )
}
