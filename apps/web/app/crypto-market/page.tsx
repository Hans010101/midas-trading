'use client'

/**
 * 加密频道 · 列表页(币种列表 / 涨幅榜)· 接真实数据(M2-D)。
 *
 * 数据走 M2-A 已有的只读端点(lib/api/crypto-market.ts):
 *   · GET /api/v1/crypto/overview      → 合约总成交额 + 恐慌贪婪指数
 *   · GET /api/v1/crypto/tickers/24h   → 榜单(交易对/最新价/涨跌/高低/成交额)+ BTC/ETH 价
 *
 * 红线 · 真实 vs 待补(逐列):
 *   ✅ 真实(ticker):交易对 / 最新价 / 24H 涨跌% / 24H 最高 / 24H 最低 / 24H 成交额
 *   ⏳ 待补(无榜单级接口,逐 symbol futures 端点才有,显示「—」):
 *        资金费率 / 账户多空比 / OI 24H 变化
 *   接不上一律「—」/ 空态,绝不伪造。M2-A 采集币种有限,有多少真实币种显示多少。
 *
 * 交互:
 *   · 行点击 → 新标签打开 /crypto-preview?symbol=<BTCUSDT>(详情页本步不改)
 *   · Tab 合约/现货 → 切 instrument 重新拉真实 ticker
 *   · 排序 → 仅对有真实数据的列(24H 涨跌% / 24H 成交额)· 前端排序
 *   · 搜索 → 后端无搜索接口,前端对已加载列表按交易对过滤
 */

import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { MarketSwitcher } from '@/components/layout/market-switcher'
import { TopNav } from '@/components/layout/top-nav'
import {
  fetchCryptoOverview,
  fetchTickers24h,
  type Instrument,
} from '@/lib/api/crypto-market'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 20

// 仅有真实数据的列可排序
type SortKey = 'chgPct' | 'turnover'

// ── 格式化 ──────────────────────────────────────────────────────────────────
function fmtPrice(n: number): string {
  if (n >= 1) return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return n.toFixed(4)
}
function fmtUsd(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}
function toBinanceSymbol(ccxt: string): string {
  return ccxt.replace('/', '') // 'BTC/USDT' → 'BTCUSDT'
}

export default function CryptoMarketPage() {
  const [tab, setTab] = useState<Instrument>('perp')
  const [sortKey, setSortKey] = useState<SortKey>('chgPct')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')

  const overviewQ = useQuery({
    queryKey: ['crypto-overview'],
    queryFn: ({ signal }) => fetchCryptoOverview(signal),
    retry: 0,
    staleTime: 60_000,
  })

  const tickersQ = useQuery({
    queryKey: ['crypto-tickers', tab],
    queryFn: ({ signal }) => fetchTickers24h(tab, 100, signal),
    retry: 0,
    staleTime: 60_000,
  })

  const allItems = useMemo(() => tickersQ.data?.items ?? [], [tickersQ.data])

  // 搜索(前端过滤)+ 排序(前端,仅真实列)
  const viewRows = useMemo(() => {
    const q = query.trim().toUpperCase()
    const filtered = q ? allItems.filter((it) => it.symbol.toUpperCase().includes(q)) : allItems
    const get = (it: (typeof allItems)[number]) =>
      sortKey === 'chgPct' ? it.change_pct_24h : it.quote_volume_24h
    const dir = sortDir === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => (get(a) - get(b)) * dir)
  }, [allItems, query, sortKey, sortDir])

  const totalPages = Math.max(1, Math.ceil(viewRows.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const pageRows = viewRows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  // 指标卡数据(真实;缺失 → null → 显示「—」)
  const ov = overviewQ.data?.market_overview
  const findPx = (sym: string) => allItems.find((it) => it.symbol === sym) ?? null
  const btc = findPx('BTC/USDT')
  const eth = findPx('ETH/USDT')
  const fgiOk = !!ov && ov.fear_greed_value > 0 && ov.fear_greed_classification !== '' && ov.fear_greed_classification !== 'N/A'

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('desc') }
    setPage(1)
  }
  function switchTab(t: Instrument) { setTab(t); setPage(1) }
  function openDetail(ccxtSymbol: string) {
    window.open(`/crypto-preview?symbol=${toBinanceSymbol(ccxtSymbol)}`, '_blank', 'noopener,noreferrer')
  }

  const fmtPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <div className="shrink-0 border-b border-paper bg-background px-6 py-2">
        <MarketSwitcher />
      </div>

      <main className="flex-1">
        <div className="border-b border-dashed border-gold/60 bg-gold/10 px-6 py-2 text-center text-xs text-gold">
          加密市场 · 真实行情(M2-A /api/v1/crypto/*)· 资金费率/多空比/OI 暂无榜单级数据显示「—」· 点行进详情页
        </div>

        <div className="mx-auto max-w-[1600px] px-6 py-5">
          <div className="mb-4">
            <h1 className="font-serif text-2xl font-bold text-midas-red">加密市场</h1>
          </div>

          {/* 顶部 4 指标卡 */}
          <div className="mb-5 grid grid-cols-2 gap-4 md:grid-cols-4">
            <MetricCard
              label="24H 合约总成交额"
              loading={overviewQ.isPending}
              value={ov && ov.derivatives_volume_24h_usd > 0 ? fmtUsd(ov.derivatives_volume_24h_usd) : '—'}
            />
            <MetricCard
              label="恐慌贪婪指数"
              loading={overviewQ.isPending}
              value={fgiOk ? String(ov!.fear_greed_value) : '—'}
              sub={fgiOk ? ov!.fear_greed_classification : '暂无数据'}
              tone="bull"
            />
            <MetricCard
              label="BTC 价格"
              loading={tickersQ.isPending}
              value={btc ? `$${fmtPrice(btc.last_price)}` : '—'}
              sub={btc ? fmtPct(btc.change_pct_24h) : '暂无数据'}
              tone={btc ? (btc.change_pct_24h >= 0 ? 'bull' : 'bear') : undefined}
            />
            <MetricCard
              label="ETH 价格"
              loading={tickersQ.isPending}
              value={eth ? `$${fmtPrice(eth.last_price)}` : '—'}
              sub={eth ? fmtPct(eth.change_pct_24h) : '暂无数据'}
              tone={eth ? (eth.change_pct_24h >= 0 ? 'bull' : 'bear') : undefined}
            />
          </div>

          {/* 工具条 */}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex overflow-hidden rounded-md border border-paper text-sm">
              <button type="button" onClick={() => switchTab('perp')}
                className={cn('px-4 py-1.5 transition-colors', tab === 'perp' ? 'bg-midas-red text-white' : 'text-muted-foreground hover:bg-midas-red-glow/50')}>
                合约 24H 涨幅榜
              </button>
              <button type="button" onClick={() => switchTab('spot')}
                className={cn('px-4 py-1.5 transition-colors', tab === 'spot' ? 'bg-midas-red text-white' : 'text-muted-foreground hover:bg-midas-red-glow/50')}>
                现货 24H 涨幅榜
              </button>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-md border border-paper bg-cream/40 px-3 py-1.5 text-sm">
                <SearchIcon />
                <input type="text" value={query} onChange={(e) => { setQuery(e.target.value); setPage(1) }}
                  placeholder="搜索交易对(前端过滤)"
                  className="w-44 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50" />
              </div>
              <button type="button" title="刷新" onClick={() => { void overviewQ.refetch(); void tickersQ.refetch() }}
                className="flex items-center gap-1.5 rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-midas-red hover:text-midas-red">
                <RefreshIcon />刷新
              </button>
            </div>
          </div>

          {/* 榜单表格 */}
          <div className="overflow-x-auto rounded-lg border border-paper">
            <table className="w-full min-w-[1100px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-paper bg-cream/50 text-xs text-muted-foreground">
                  <th className="w-12 px-3 py-2 text-center font-medium">#</th>
                  <th className="px-3 py-2 text-left font-medium">交易对</th>
                  <th className="px-3 py-2 text-right font-medium">最新价格</th>
                  <SortTh label="24H 涨跌%" col="chgPct" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <th className="px-3 py-2 text-right font-medium">24H 最高</th>
                  <th className="px-3 py-2 text-right font-medium">24H 最低</th>
                  <th className="px-3 py-2 text-right font-medium" title="无榜单级接口 · 待补">资金费率</th>
                  <th className="px-3 py-2 text-right font-medium" title="无榜单级接口 · 待补">账户多空比</th>
                  <th className="px-3 py-2 text-right font-medium" title="无榜单级接口 · 待补">OI 24H 变化</th>
                  <SortTh label="24H 成交额" col="turnover" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {tickersQ.isPending && <StateRow text="加载中…" />}
                {tickersQ.isError && <StateRow text="暂时无法读取行情(后端不可达)" />}
                {tickersQ.isSuccess && viewRows.length === 0 && (
                  <StateRow text={query ? '无匹配交易对' : '暂无行情数据 · 待采集'} />
                )}
                {tickersQ.isSuccess && pageRows.map((r, i) => {
                  const rank = (safePage - 1) * PAGE_SIZE + i + 1
                  return (
                    <tr key={r.symbol} onClick={() => openDetail(r.symbol)} title="点击在新标签打开详情页"
                      className="group cursor-pointer border-b border-paper/60 transition-colors hover:bg-midas-red-glow/30">
                      <td className="px-3 py-2.5 text-center font-mono text-xs text-muted-foreground/70">{rank}</td>
                      <td className="px-3 py-2.5"><span className="font-serif font-bold text-foreground">{r.symbol}</span></td>
                      <Td>{fmtPrice(r.last_price)}</Td>
                      <Td className={r.change_pct_24h >= 0 ? 'text-bull' : 'text-bear'}>{fmtPct(r.change_pct_24h)}</Td>
                      <Td className="text-muted-foreground/80">{fmtPrice(r.high_24h)}</Td>
                      <Td className="text-muted-foreground/80">{fmtPrice(r.low_24h)}</Td>
                      <Td className="text-muted-foreground/40">—</Td>
                      <Td className="text-muted-foreground/40">—</Td>
                      <Td className="text-muted-foreground/40">—</Td>
                      <Td className="text-muted-foreground/80">{fmtUsd(r.quote_volume_24h)}</Td>
                      <td className="px-2 text-center text-muted-foreground/30 transition-colors group-hover:text-midas-red">›</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* 分页(按实际真实币种数)*/}
          <div className="mt-4 flex items-center justify-between">
            <span className="text-xs text-muted-foreground/70">
              共 {viewRows.length} 个 · 第 {safePage}/{totalPages} 页(每页 {PAGE_SIZE})
            </span>
            {totalPages > 1 && <Pagination page={safePage} totalPages={totalPages} onChange={setPage} />}
          </div>

          <p className="mt-3 text-[11px] text-muted-foreground/60">
            交易对/价格/涨跌/高低/成交额 = 真实(M2-A ticker)· 资金费率/多空比/OI = 暂无榜单级接口显示「—」·
            点行新标签打开详情页 · 仅供参考,不构成投资建议
          </p>
        </div>
      </main>
    </div>
  )
}

// ── 指标卡 ──────────────────────────────────────────────────────────────────
function MetricCard({
  label, value, sub, tone, loading,
}: { label: string; value: string; sub?: string; tone?: 'bull' | 'bear'; loading?: boolean }) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 font-mono text-2xl font-bold', tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : 'text-foreground')}>
        {loading ? '…' : value}
      </div>
      {sub && <div className={cn('mt-0.5 text-[11px]', tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : 'text-muted-foreground/70')}>{loading ? '' : sub}</div>}
    </div>
  )
}

// ── 可排序表头(仅真实列)──────────────────────────────────────────────────
function SortTh({
  label, col, sortKey, sortDir, onSort,
}: { label: string; col: SortKey; sortKey: SortKey; sortDir: 'asc' | 'desc'; onSort: (k: SortKey) => void }) {
  const active = sortKey === col
  return (
    <th className="px-3 py-2 text-right font-medium">
      <button type="button" onClick={() => onSort(col)} title={`按${label}排序`}
        className={cn('inline-flex items-center gap-1 transition-colors hover:text-midas-red', active ? 'font-bold text-midas-red' : 'text-muted-foreground')}>
        {label}
        <span className="flex flex-col leading-[0.5]">
          <span className={cn('text-[8px]', active && sortDir === 'asc' ? 'text-midas-red' : 'text-muted-foreground/35')}>▲</span>
          <span className={cn('text-[8px]', active && sortDir === 'desc' ? 'text-midas-red' : 'text-muted-foreground/35')}>▼</span>
        </span>
      </button>
    </th>
  )
}

function Pagination({ page, totalPages, onChange }: { page: number; totalPages: number; onChange: (p: number) => void }) {
  const btn = 'flex h-7 min-w-7 items-center justify-center rounded-md border border-paper px-2 text-xs transition-colors'
  return (
    <div className="flex items-center gap-1">
      <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}
        className={cn(btn, page <= 1 ? 'cursor-not-allowed text-muted-foreground/30' : 'text-muted-foreground hover:border-midas-red hover:text-midas-red')}>
        上一页
      </button>
      {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
        <button key={p} type="button" onClick={() => onChange(p)}
          className={cn(btn, p === page ? 'border-midas-red bg-midas-red text-white' : 'text-muted-foreground hover:border-midas-red hover:text-midas-red')}>
          {p}
        </button>
      ))}
      <button type="button" disabled={page >= totalPages} onClick={() => onChange(page + 1)}
        className={cn(btn, page >= totalPages ? 'cursor-not-allowed text-muted-foreground/30' : 'text-muted-foreground hover:border-midas-red hover:text-midas-red')}>
        下一页
      </button>
    </div>
  )
}

function StateRow({ text }: { text: string }) {
  return (
    <tr>
      <td colSpan={11} className="px-3 py-10 text-center text-sm text-muted-foreground/60">{text}</td>
    </tr>
  )
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn('px-3 py-2.5 text-right font-mono tabular-nums', className)}>{children}</td>
}

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground/50">
      <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
    </svg>
  )
}
function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v5h-5" />
    </svg>
  )
}
