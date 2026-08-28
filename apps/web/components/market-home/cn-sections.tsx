'use client'

/**
 * A股榜单区(0023 阶段③ · 3.2)· 仅 /cn-market 渲染 · 接 /api/v1/cn/board。
 *
 * 三块:市场情绪条(涨跌平家数 + 涨跌停估)+ 3 榜单 Tab(涨幅/跌幅/成交额)+ 行业板块。
 * 用 0022 阶段② 共用组件(Panel / DataTable / EmptyState / LoadingNote)。
 * 换手率/量比本期不渲染(Sina 无字段 · 东财不可达)· 个股详情页 3.4 上线(本期行不可点)。
 * 红线:只读行情。
 */

import { useEffect, useMemo, useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { SectorHeatmap } from '@/components/market-home/sector-heatmap'
import { DataTable, TCell, TH, THead, TRow } from '@/components/ui/data-table'
import { Panel } from '@/components/ui/panel'
import { DataTimestamp, EmptyState, LoadingNote } from '@/components/ui/state'
import { fetchCnBoard, searchCnSpot, type CnBreadth, type CnSpotRow } from '@/lib/api/cn-market'
import {
  cnCompanyNameFromOriginal,
  cnSectorName,
  cnStockName,
} from '@/lib/i18n/market-copy'
import { detailHref } from '@/lib/seo/detail-symbols'
import { cn } from '@/lib/utils'

type Tab = 'gainers' | 'losers' | 'amount'
const TABS: { key: Tab; zh: string; en: string }[] = [
  { key: 'gainers', zh: '涨幅榜', en: 'Top gainers' },
  { key: 'losers', zh: '跌幅榜', en: 'Top losers' },
  { key: 'amount', zh: '成交额榜', en: 'Top turnover' },
]

function fmtPct(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}
function fmtPrice(n: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtAmount(n: number, locale: 'en' | 'zh'): string {
  if (locale === 'en') {
    if (n >= 1e12) return `CNY ${(n / 1e12).toFixed(2)}T`
    if (n >= 1e9) return `CNY ${(n / 1e9).toFixed(2)}B`
    if (n >= 1e6) return `CNY ${(n / 1e6).toFixed(1)}M`
    return `CNY ${n.toFixed(0)}`
  }
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)}亿`
  if (n >= 1e4) return `${(n / 1e4).toFixed(0)}万`
  return n.toFixed(0)
}
const upDown = (n: number) => (n >= 0 ? 'text-up' : 'text-down')

// 行点击 → 新标签打开 A股个股详情页(纯做多下单)· 同 crypto-market 模式
function openDetail(symbol: string, name: string) {
  // SEO 批7:curated → 路径段 SEO 页 · 非 curated → 旧 ?symbol=(detailHref 统一判定)
  window.open(detailHref({ symbol, market: 'cn', name }), '_blank', 'noopener,noreferrer')
}

export function CnSections() {
  const { locale } = useRuntimeLocale()
  const q = useQuery({
    queryKey: ['cn-board'],
    queryFn: ({ signal }) => fetchCnBoard(100, signal),
    retry: 0,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const [tab, setTab] = useState<Tab>('gainers')
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')

  // 搜索输入防抖 300ms → 减少 /cn/search 请求(全市场搜索走后端)
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query.trim()), 300)
    return () => clearTimeout(t)
  }, [query])

  // 全市场搜索(后端 /cn/search · 覆盖 ~5500)· 仅在有关键词时启用
  const searchQ = useQuery({
    queryKey: ['cn-search', debouncedQuery],
    queryFn: ({ signal }) => searchCnSpot(debouncedQuery, 30, signal),
    enabled: debouncedQuery.length > 0,
    retry: 0,
    staleTime: 30_000,
  })
  const isSearching = debouncedQuery.length > 0

  const breadth = q.data?.breadth ?? null
  const boardRows: CnSpotRow[] =
    tab === 'gainers'
      ? (q.data?.gainers ?? [])
      : tab === 'losers'
        ? (q.data?.losers ?? [])
        : (q.data?.top_amount ?? [])
  const sectors = q.data?.sectors
  const localizedSectors = useMemo(
    () => (sectors ?? []).map((sector, index) => ({
      ...sector,
      name: cnSectorName(sector.name, locale, index),
      leader_name: cnCompanyNameFromOriginal(sector.leader_name, locale),
    })),
    [locale, sectors],
  )
  const formatAmount = (n: number) => fmtAmount(n, locale)
  // 搜索态 → 显示搜索结果(替代榜单);否则显示当前 tab 前 100
  const rows = isSearching ? (searchQ.data ?? []) : boardRows

  return (
    <div className="mt-8 space-y-6">
      {/* 市场情绪条 */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-serif text-sm font-bold text-foreground">
            {locale === 'en'
              ? 'Market breadth · Full A-share market'
              : `市场情绪 · ${q.data?.scope_label ?? 'A股全市场'}`}
          </h2>
          <div className="flex items-center gap-3">
            <DataTimestamp value={q.data?.data_as_of} locale={locale} className="hidden sm:inline" />
            {q.data?.pool_size !== undefined && (
              <span className="text-xs text-muted-foreground/70">
                {locale === 'en'
                  ? `${q.data.pool_size} stocks · Full-market universe`
                  : `覆盖 ${q.data.pool_size} 只 A 股`}
              </span>
            )}
          </div>
        </div>
        {q.isPending && <LoadingNote className="py-6" />}
        {q.isError && (
          <EmptyState
            title={locale === 'en' ? 'Rankings are temporarily unavailable' : '暂时无法读取榜单'}
            hint={locale === 'en' ? 'The data service will retry automatically' : '后端不可达 · 稍后自动重试'}
          />
        )}
        {q.isSuccess && !breadth && (
          <EmptyState
            title={locale === 'en' ? 'Ranking data is awaiting collection' : '榜单数据待采集'}
            hint={locale === 'en' ? 'Collected every three minutes during A-share market hours' : 'A股交易时段自动采集(每 3 分钟)'}
          />
        )}
        {breadth && <BreadthBar b={breadth} locale={locale} />}
      </section>

      {/* 行业板块热力图(上移到榜单前 · 当市场概览)*/}
      {q.isSuccess && localizedSectors.length > 0 && (
        <section>
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h2 className="font-serif text-sm font-bold text-foreground">
              {locale === 'en' ? 'Sectors' : '行业板块'}
            </h2>
            <span className="text-xs text-muted-foreground/70">
              {locale === 'en'
                ? 'Turnover-weighted · Top 24 sectors · Color intensity reflects performance'
                : '成交额加权 · 取主要 24 板块 · 色深=涨跌幅强弱 · 悬停看领涨/家数/成交额'}
            </span>
          </div>
          <SectorHeatmap sectors={localizedSectors} fmtAmount={formatAmount} max={24} />
        </section>
      )}

      {/* 榜单 3 Tab */}
      {q.isSuccess && breadth && (
        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            {/* 搜索态隐藏 tab(搜索是全市场,与涨跌/成交额排序无关)*/}
            {isSearching ? (
              <span className="text-sm text-muted-foreground">
                {locale === 'en' ? 'A-share search results' : 'A股全市场搜索结果'}
              </span>
            ) : (
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
                    {t[locale]}
                  </button>
                ))}
              </div>
            )}
            {/* 搜索框 · 服务端搜全市场 ~5500(覆盖榜单外的标的)*/}
            <div className="flex items-center gap-1.5 rounded-md border border-paper bg-surface-card px-3 py-1.5 text-sm">
              <SearchIcon />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={locale === 'en' ? 'Search A-shares by code or name' : '搜索 A股全市场(代码 / 名称)'}
                className="w-52 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
              />
            </div>
          </div>
          <DataTable minWidth="640px">
            <THead>
              <TH align="center">#</TH>
              <TH>{locale === 'en' ? 'Code' : '代码'}</TH>
              <TH>{locale === 'en' ? 'Company' : '名称'}</TH>
              <TH align="right">{locale === 'en' ? 'Last price' : '最新价'}</TH>
              <TH align="right">{locale === 'en' ? 'Change' : '涨跌幅'}</TH>
              <TH align="right">{locale === 'en' ? 'Turnover' : '成交额'}</TH>
            </THead>
            <tbody>
              {isSearching && searchQ.isPending && (
                <TRow>
                  <TCell align="center" className="py-8 text-muted-foreground/60" colSpan={6}>
                    {locale === 'en' ? 'Searching…' : '搜索中…'}
                  </TCell>
                </TRow>
              )}
              {!(isSearching && searchQ.isPending) && rows.length === 0 && (
                <TRow>
                  <TCell align="center" className="py-8 text-muted-foreground/60" colSpan={6}>
                    {isSearching
                      ? locale === 'en' ? 'No matches. Try a six-digit A-share code.' : '无匹配标的(试试代码或名称)'
                      : locale === 'en' ? 'No data available' : '暂无数据'}
                  </TCell>
                </TRow>
              )}
              {rows.map((r, i) => (
                <TRow
                  key={r.symbol}
                  onClick={() => openDetail(r.symbol, cnStockName(r.symbol, r.name, locale))}
                  className="cursor-pointer transition-colors hover:bg-midas-red-glow/30"
                  title={locale === 'en' ? 'Open stock details' : '点击查看详情 · 下单'}
                >
                  <TCell align="center" mono className="text-xs text-muted-foreground/70">
                    {i + 1}
                  </TCell>
                  <TCell mono>{r.symbol}</TCell>
                  <TCell className="font-medium text-foreground">
                    {cnStockName(r.symbol, r.name, locale)}
                  </TCell>
                  <TCell align="right" mono>
                    {fmtPrice(r.last_price)}
                  </TCell>
                  <TCell align="right" mono className={upDown(r.change_pct)}>
                    {fmtPct(r.change_pct)}
                  </TCell>
                  <TCell align="right" mono className="text-muted-foreground/80">
                    {fmtAmount(r.amount, locale)}
                  </TCell>
                </TRow>
              ))}
            </tbody>
          </DataTable>
          <p className="mt-2 text-center text-[11px] text-muted-foreground/60">
            {isSearching
              ? locale === 'en'
                ? `${rows.length} matches · Select a row for details`
                : `命中 ${rows.length} 只 · 点击看详情`
              : locale === 'en'
                ? `${q.data?.pool_size ?? rows.length} stocks · Full-market snapshot`
                : `全市场 ${q.data?.pool_size ?? rows.length} 只 · 定时更新`}
          </p>
        </section>
      )}

    </div>
  )
}

function BreadthBar({ b, locale }: { b: CnBreadth; locale: 'en' | 'zh' }) {
  const total = b.up_count + b.down_count + b.flat_count || 1
  const upPct = (b.up_count / total) * 100
  const flatPct = (b.flat_count / total) * 100
  const downPct = (b.down_count / total) * 100
  return (
    <Panel padding="md">
      <div className="flex items-center justify-between font-mono text-sm">
        <span className="font-bold text-up">
          {locale === 'en' ? `${b.up_count} Up` : `${b.up_count} 涨`}
        </span>
        <span className="text-muted-foreground">
          {locale === 'en' ? `${b.flat_count} Flat` : `${b.flat_count} 平`}
        </span>
        <span className="font-bold text-down">
          {locale === 'en' ? `${b.down_count} Down` : `${b.down_count} 跌`}
        </span>
      </div>
      <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-paper">
        <div className="bg-up" style={{ width: `${upPct}%` }} />
        <div className="bg-muted/50" style={{ width: `${flatPct}%` }} />
        <div className="bg-down" style={{ width: `${downPct}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>
          {locale === 'en' ? 'Limit up ' : '涨停 '}
          <b className="font-mono text-up">{b.limit_up_count}</b>
          {locale === 'en' ? ' · Limit down ' : ' · 跌停 '}
          <b className="font-mono text-down">{b.limit_down_count}</b>
          <span className="ml-1 text-muted-foreground/50">
            {locale === 'en' ? '(estimated from price-limit thresholds)' : '(按涨跌幅阈值估算)'}
          </span>
        </span>
        <span>
          {locale === 'en' ? 'Total market turnover ' : '两市成交额 '}
          <b className="font-mono text-foreground">{fmtAmount(b.total_amount, locale)}</b>
        </span>
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
