'use client'

/**
 * 美股榜单区(0023 阶段③ · 3.3)· 仅 /us-market 渲染 · 接 /api/v1/us/board。
 *
 * 决策⑥:策展池(重点关注池 · 非全市场)· 顶部诚实标注。
 * 三块:重点关注池 涨幅/跌幅/成交额 3 榜单 Tab + 行业板块 + 中概股板块(板块表里高亮)。
 * 用 0022 阶段② 共用组件。成交额为美元估(close×volume)· 盘前盘后异动本期不做。
 * 个股详情页 3.4 上线(本期行不可点)· 红线:只读行情。
 */

import { useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { SectorHeatmap } from '@/components/market-home/sector-heatmap'
import { DataTable, TCell, TH, THead, TRow } from '@/components/ui/data-table'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { fetchUsBoard, type UsSpotRow } from '@/lib/api/us-market'
import { usSectorName, usStockName } from '@/lib/i18n/market-copy'
import { detailHref } from '@/lib/seo/detail-symbols'
import { cn } from '@/lib/utils'

type Tab = 'gainers' | 'losers' | 'amount'
const TABS: readonly Tab[] = ['gainers', 'losers', 'amount']

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

// 行点击 → 新标签打开美股个股详情页(做多 + 卖空下单)· 同 crypto-market 模式
function openDetail(symbol: string, name: string) {
  // SEO 批7:curated → 路径段 SEO 页 · 非 curated → 旧 ?symbol=(detailHref 统一判定)
  window.open(detailHref({ symbol, market: 'us', name }), '_blank', 'noopener,noreferrer')
}

export function UsSections() {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const q = useQuery({
    queryKey: ['us-board'],
    queryFn: ({ signal }) => fetchUsBoard(128, signal),
    retry: 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const [tab, setTab] = useState<Tab>('gainers')
  const [query, setQuery] = useState('')

  const poolSize = q.data?.pool_size ?? 0
  // 全策展池(limit=128 → gainers 即全池 · 搜索覆盖整池,与 tab 排序无关)
  const fullPool = q.data?.gainers ?? []
  const boardRows: UsSpotRow[] =
    tab === 'gainers'
      ? (q.data?.gainers ?? [])
      : tab === 'losers'
        ? (q.data?.losers ?? [])
        : (q.data?.top_amount ?? [])
  const sectors = q.data?.sectors ?? []
  const localizedSectors = sectors.map((sector, index) => ({
    ...sector,
    name: usSectorName(sector.name, locale, index),
  }))

  const isSearching = query.trim().length > 0
  const ql = query.trim().toLowerCase()
  // 本地过滤整池 128(代码 / 名称)· 池小,前端过滤轻(同港股本地过滤)
  const searchRows = isSearching
    ? fullPool.filter(
        (r) =>
          r.symbol.toLowerCase().includes(ql)
          || r.name.toLowerCase().includes(ql)
          || usStockName(r.symbol, r.name, locale).toLowerCase().includes(ql),
      )
    : []
  // 搜索态 → 过滤结果(整池 128);否则当前 tab 前 100
  const rows = isSearching ? searchRows : boardRows.slice(0, 100)

  return (
    <div className="mt-8 space-y-6">
      {/* 行业板块热力图(上移到榜单前 · 当市场概览)*/}
      {q.isSuccess && localizedSectors.length > 0 && (
        <section>
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h2 className="font-serif text-sm font-bold text-foreground">
              {en ? 'Sectors · China ADRs' : '行业板块 · 中概股板块'}
            </h2>
            <span className="text-xs text-muted-foreground/70">
              {en
                ? 'Equal-weighted · Color intensity reflects performance · Hover for count and turnover'
                : '等权均值 · 色深=涨跌幅强弱 · 悬停看领涨/家数/成交额'}
            </span>
          </div>
          <SectorHeatmap sectors={localizedSectors} fmtAmount={fmtUsd} />
        </section>
      )}

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-serif text-sm font-bold text-foreground">
            {en ? 'U.S. stock movers · Curated universe' : '热门美股 · 重点关注池'}
          </h2>
          {poolSize > 0 && (
            <span className="text-xs text-muted-foreground/70">
              {en
                ? `${poolSize} stocks · Curated universe, not the full market`
                : `池内 ${poolSize} 只 · 策展非全市场`}
            </span>
          )}
        </div>
        {q.isPending && <LoadingNote className="py-6" />}
        {q.isError && (
          <EmptyState
            title={en ? 'U.S. rankings are temporarily unavailable' : '暂时无法读取榜单'}
            hint={en ? 'The data service will retry automatically' : '后端不可达 · 稍后自动重试'}
          />
        )}
        {q.isSuccess && poolSize === 0 && (
          <EmptyState
            title={en ? 'U.S. ranking data is awaiting collection' : '榜单数据待采集'}
            hint={
              en
                ? 'Snapshots are collected every five minutes during U.S. market hours'
                : '美股交易时段自动采集(每 5 分钟)'
            }
          />
        )}

        {q.isSuccess && poolSize > 0 && (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              {/* 搜索态隐藏 tab(搜索覆盖整池,与涨跌/成交额排序无关)*/}
              {isSearching ? (
                <span className="text-sm text-muted-foreground">
                  {en ? 'Curated universe search results' : '重点关注池搜索结果'}
                </span>
              ) : (
                <div className="flex overflow-hidden rounded-md border border-paper text-sm">
                  {TABS.map((tabKey) => (
                    <button
                      key={tabKey}
                      type="button"
                      onClick={() => setTab(tabKey)}
                      className={cn(
                        'px-4 py-1.5 transition-colors',
                        tab === tabKey
                          ? 'bg-midas-red text-white'
                          : 'text-muted-foreground hover:bg-midas-red-glow/50',
                      )}
                    >
                      {tabKey === 'gainers'
                        ? en ? 'Top gainers' : '涨幅榜'
                        : tabKey === 'losers'
                          ? en ? 'Top losers' : '跌幅榜'
                          : en ? 'Top turnover' : '成交额榜'}
                    </button>
                  ))}
                </div>
              )}
              {/* 搜索框 · 本地过滤策展池 128(★非全美股 · 池外搜不到)*/}
              <div className="flex items-center gap-1.5 rounded-md border border-paper bg-surface-card px-3 py-1.5 text-sm">
                <SearchIcon />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={
                    en
                      ? 'Search the curated U.S. universe'
                      : '搜索重点关注池(非全美股)'
                  }
                  className="w-56 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
                />
              </div>
            </div>
            <DataTable minWidth="640px">
              <THead>
                <TH align="center">#</TH>
                <TH>{en ? 'Symbol' : '代码'}</TH>
                <TH>{en ? 'Company' : '名称'}</TH>
                <TH>{en ? 'Sector' : '板块'}</TH>
                <TH align="right">{en ? 'Last price' : '最新价'}</TH>
                <TH align="right">{en ? 'Change' : '涨跌幅'}</TH>
                <TH align="right">{en ? 'Turnover' : '成交额'}</TH>
              </THead>
              <tbody>
                {rows.length === 0 && (
                  <TRow>
                    <TCell align="center" className="py-8 text-muted-foreground/60" colSpan={7}>
                      {isSearching
                        ? en
                          ? 'No matches in the curated universe'
                          : '无匹配(池内仅策展 128 只 · 池外搜不到)'
                        : en ? 'No data' : '暂无数据'}
                    </TCell>
                  </TRow>
                )}
                {rows.map((r, i) => (
                  <TRow
                    key={r.symbol}
                    onClick={() => openDetail(r.symbol, r.name)}
                    className="cursor-pointer transition-colors hover:bg-midas-red-glow/30"
                    title={en ? 'Open details · Long or short' : '点击查看详情 · 做多 / 卖空下单'}
                  >
                    <TCell align="center" mono className="text-xs text-muted-foreground/70">
                      {i + 1}
                    </TCell>
                    <TCell mono>{r.symbol}</TCell>
                    <TCell className="font-medium text-foreground">
                      {usStockName(r.symbol, r.name, locale)}
                    </TCell>
                    <TCell className="text-xs text-muted-foreground/70">
                      {usSectorName(r.sector, locale)}
                    </TCell>
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
            <p className="mt-2 text-center text-[11px] text-muted-foreground/60">
              {isSearching
                ? en
                  ? `${rows.length} matches · Select a row for details`
                  : `池内命中 ${rows.length} 只 · 点击看详情`
                : en
                  ? `${poolSize} stocks in the current universe · Updated on schedule`
                  : `当前重点池 ${poolSize} 只 · 定时更新`}
            </p>
          </>
        )}
      </section>

    </div>
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
