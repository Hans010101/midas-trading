'use client'

/**
 * 加密频道 · 列表页(币种列表 / 涨幅榜)· 静态布局骨架(v2)。
 *
 * ⚠ 仍是【布局骨架】· 不接真实数据:所有指标卡 / 表格行 = 占位示意值。
 *   · 顶部全站导航栏 = 复用现有 <TopNav />(本页"住进"全站布局,不新写导航)
 *   · 分页:每页 20 · 占位铺到 100 个(5 页)· 真实「前 100 币种」由采集端后续扩容
 *   · 排序:5 列可点(24H涨跌% / 资金费率 / 账户多空比 / OI 24H变化 / 24H成交额)·
 *           默认 24H涨跌% 降序(= 涨幅榜)
 *   · 搜索 / 刷新 = 纯视觉 · 行可点视觉示意进详情页(/crypto-preview · 跳转下一步接)
 *
 * 视觉:点金视觉系统 · 帝王金主色 · 涨红(#DC143C)/ 跌绿(#0F6E5F)·
 *       多空占比小色条 多=青绿 / 空=浅红(沿用详情页 6 维度图配色)。
 * 预览:本地 pnpm dev → /crypto-market
 */

import { useMemo, useState } from 'react'

import { MarketSwitcher } from '@/components/layout/market-switcher'
import { TopNav } from '@/components/layout/top-nav'
import { cn } from '@/lib/utils'

// ── 占位示意数据(纯静态 · 非真实)· 确定性生成 100 条 ─────────────────────────
interface Row {
  symbol: string
  price: number
  chgPct: number // 24H 涨跌 %
  high: number
  low: number
  funding: number // 资金费率 %
  longPct: number // 账户多空 · 多方占比 0..100
  oiChg: number // OI 24H 变化 %
  turnover: number // 24H 成交额(USD)
}

// 伪随机(确定性 · 仅占位)
function rng(seed: number): number {
  const x = Math.sin(seed * 127.1) * 43758.5453
  return x - Math.floor(x)
}

const BASES = [
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'AVAX', 'LINK', 'TON',
  'TRX', 'LTC', 'DOT', 'MATIC', 'SHIB', 'UNI', 'BCH', 'ATOM', 'ETC', 'XLM',
  'NEAR', 'APT', 'ARB', 'OP', 'FIL', 'INJ', 'SUI', 'SEI', 'TIA', 'STX',
  'PEPE', 'WIF', 'BONK', 'FTM', 'RUNE', 'AAVE', 'MKR', 'LDO', 'IMX', 'GRT',
  'SAND', 'AXS', 'EOS', 'EGLD', 'FLOW', 'CHZ', 'GALA', 'ENJ', 'ZIL', 'CRV',
]
const BASE_PRICE: Record<string, number> = {
  BTC: 64820, ETH: 3142, SOL: 148.3, BNB: 592.4, XRP: 0.5218, DOGE: 0.1402,
  ADA: 0.4471, AVAX: 28.74, LINK: 14.06, TON: 6.812,
}

const ROWS: Row[] = Array.from({ length: 100 }, (_, i) => {
  const base = BASES[i] ?? `ALT${i + 1}`
  const price = BASE_PRICE[base] ?? +(rng(i + 11) * 80 + 0.5).toFixed(rng(i + 11) > 0.5 ? 2 : 4)
  const chgPct = +(rng(i + 1) * 22 - 9).toFixed(2) // -9 .. +13
  const funding = +(rng(i + 7) * 0.04 - 0.014).toFixed(3)
  const longPct = Math.round(35 + rng(i + 3) * 42) // 35 .. 77
  const oiChg = +(rng(i + 5) * 32 - 13).toFixed(1)
  const turnover = Math.round(rng(i + 9) * 12_000) * 1e6 // 0 .. 12B
  const swing = 1 + rng(i + 13) * 0.04
  return {
    symbol: `${base}/USDT`,
    price,
    chgPct,
    high: +(price * swing).toPrecision(6),
    low: +(price / swing).toPrecision(6),
    funding,
    longPct,
    oiChg,
    turnover,
  }
})

const METRICS = [
  { label: '24H 合约总成交额', value: '$48.6B', sub: '示意' },
  { label: '恐慌贪婪指数', value: '72', sub: '贪婪 · 示意', tone: 'bull' as const },
  { label: 'BTC 价格', value: '$64,820', sub: '+2.34%', tone: 'bull' as const },
  { label: 'ETH 价格', value: '$3,142', sub: '+3.91%', tone: 'bull' as const },
]

const PAGE_SIZE = 20

// 可排序列 key + 取值函数
type SortKey = 'chgPct' | 'funding' | 'lsRatio' | 'oiChg' | 'turnover'
const SORT_VALUE: Record<SortKey, (r: Row) => number> = {
  chgPct: (r) => r.chgPct,
  funding: (r) => r.funding,
  lsRatio: (r) => r.longPct / Math.max(1, 100 - r.longPct), // 多空比值
  oiChg: (r) => r.oiChg,
  turnover: (r) => r.turnover,
}

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
function ratioText(longPct: number): string {
  return (longPct / Math.max(1, 100 - longPct)).toFixed(2)
}

export default function CryptoMarketPage() {
  const [tab, setTab] = useState<'perp' | 'spot'>('perp')
  const [sortKey, setSortKey] = useState<SortKey>('chgPct')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)

  const sortedRows = useMemo(() => {
    const get = SORT_VALUE[sortKey]
    const dir = sortDir === 'asc' ? 1 : -1
    return [...ROWS].sort((a, b) => (get(a) - get(b)) * dir)
  }, [sortKey, sortDir])

  const totalPages = Math.ceil(sortedRows.length / PAGE_SIZE)
  const pageRows = sortedRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc') // 切到新列默认降序
    }
    setPage(1) // 重排回第 1 页
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      {/* 1 · 全站共用顶部导航栏(复用现有 <TopNav /> · 不新写、不改其本体)*/}
      <TopNav />

      {/* 2 · 市场切换条(A股/美股/加密)· 全站共用 MarketSwitcher · 当前=加密高亮 */}
      <div className="shrink-0 border-b border-paper bg-background px-6 py-2">
        <MarketSwitcher />
      </div>

      <main className="flex-1">
        {/* 骨架标识条 */}
        <div className="border-b border-dashed border-gold/60 bg-gold/10 px-6 py-2 text-center text-xs text-gold">
          加密市场 · 列表页骨架 · 数值为示意 · 不接真实数据 · 点行进详情页(跳转下一步接)
        </div>

        <div className="mx-auto max-w-[1600px] px-6 py-5">
          <div className="mb-4 flex items-baseline gap-3">
            <h1 className="font-serif text-2xl font-bold text-midas-red">加密市场</h1>
            <span className="text-sm text-muted-foreground">合约 / 现货 · 24H 行情榜</span>
          </div>

          {/* 顶部 4 指标卡 */}
          <div className="mb-5 grid grid-cols-2 gap-4 md:grid-cols-4">
            {METRICS.map((m) => (
              <div key={m.label} className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
                <div className="text-xs text-muted-foreground">{m.label}</div>
                <div className={cn('mt-1 font-mono text-2xl font-bold', m.tone === 'bull' ? 'text-bull' : 'text-foreground')}>
                  {m.value}
                </div>
                <div className={cn('mt-0.5 text-[11px]', m.tone === 'bull' ? 'text-bull' : 'text-muted-foreground/70')}>
                  {m.sub}
                </div>
              </div>
            ))}
          </div>

          {/* 工具条:Tab + 搜索 + 刷新 */}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex overflow-hidden rounded-md border border-paper text-sm">
              <button type="button" onClick={() => setTab('perp')}
                className={cn('px-4 py-1.5 transition-colors', tab === 'perp' ? 'bg-midas-red text-white' : 'text-muted-foreground hover:bg-midas-red-glow/50')}>
                合约 24H 涨幅榜
              </button>
              <button type="button" onClick={() => setTab('spot')}
                className={cn('px-4 py-1.5 transition-colors', tab === 'spot' ? 'bg-midas-red text-white' : 'text-muted-foreground hover:bg-midas-red-glow/50')}>
                现货 24H 涨幅榜
              </button>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-md border border-paper bg-cream/40 px-3 py-1.5 text-sm">
                <SearchIcon />
                <input type="text" placeholder="搜索交易对(如 BTC)"
                  className="w-44 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50" />
              </div>
              <button type="button" title="刷新(示意)"
                className="flex items-center gap-1.5 rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-midas-red hover:text-midas-red">
                <RefreshIcon />刷新
              </button>
            </div>
          </div>

          {/* 币种列表表格 */}
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
                  <SortTh label="资金费率" col="funding" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <SortTh label="账户多空比" col="lsRatio" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <SortTh label="OI 24H 变化" col="oiChg" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <SortTh label="24H 成交额" col="turnover" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r, i) => {
                  const rank = (page - 1) * PAGE_SIZE + i + 1
                  return (
                    <tr key={r.symbol} title="点击进入详情页(跳转下一步接)"
                      className="group cursor-pointer border-b border-paper/60 transition-colors hover:bg-midas-red-glow/30">
                      <td className="px-3 py-2.5 text-center font-mono text-xs text-muted-foreground/70">{rank}</td>
                      <td className="px-3 py-2.5"><span className="font-serif font-bold text-foreground">{r.symbol}</span></td>
                      <Td>{fmtPrice(r.price)}</Td>
                      <Td className={r.chgPct >= 0 ? 'text-bull' : 'text-bear'}>{r.chgPct >= 0 ? '+' : ''}{r.chgPct.toFixed(2)}%</Td>
                      <Td className="text-muted-foreground/80">{fmtPrice(r.high)}</Td>
                      <Td className="text-muted-foreground/80">{fmtPrice(r.low)}</Td>
                      <Td className={r.funding >= 0 ? 'text-bull' : 'text-bear'}>{r.funding >= 0 ? '+' : ''}{r.funding.toFixed(3)}%</Td>
                      {/* 账户多空比 · 右对齐(色条 + 比值靠右,与其它数值列统一)*/}
                      <td className="px-3 py-2.5">
                        <div className="flex items-center justify-end gap-2">
                          <div className="flex h-2 w-16 overflow-hidden rounded-full bg-paper">
                            <div style={{ width: `${r.longPct}%`, backgroundColor: '#1FA383' }} />
                            <div style={{ width: `${100 - r.longPct}%`, backgroundColor: '#E8918C' }} />
                          </div>
                          <span className="w-9 text-right font-mono text-xs tabular-nums text-foreground/80">{ratioText(r.longPct)}</span>
                        </div>
                      </td>
                      <Td className={r.oiChg >= 0 ? 'text-bull' : 'text-bear'}>{r.oiChg >= 0 ? '+' : ''}{r.oiChg.toFixed(1)}%</Td>
                      <Td className="text-muted-foreground/80">{fmtUsd(r.turnover)}</Td>
                      <td className="px-2 text-center text-muted-foreground/30 transition-colors group-hover:text-midas-red">›</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* 分页控件 */}
          <div className="mt-4 flex items-center justify-between">
            <span className="text-xs text-muted-foreground/70">
              共 {sortedRows.length} 个 · 第 {page}/{totalPages} 页(每页 {PAGE_SIZE})
            </span>
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
          </div>

          <p className="mt-3 text-[11px] text-muted-foreground/60">
            数据为示意占位 · 接真实行情(/api/v1/crypto/*)+ 点行跳转详情页 + 前 100 币种采集扩容为下一步 · 仅供参考,不构成投资建议
          </p>
        </div>
      </main>
    </div>
  )
}

// ── 可排序表头 ──────────────────────────────────────────────────────────────
function SortTh({
  label, col, sortKey, sortDir, onSort,
}: {
  label: string
  col: SortKey
  sortKey: SortKey
  sortDir: 'asc' | 'desc'
  onSort: (k: SortKey) => void
}) {
  const active = sortKey === col
  return (
    <th className="px-3 py-2 text-right font-medium">
      <button
        type="button"
        onClick={() => onSort(col)}
        className={cn(
          'inline-flex items-center gap-1 transition-colors hover:text-midas-red',
          active ? 'font-bold text-midas-red' : 'text-muted-foreground',
        )}
        title={`按${label}排序`}
      >
        {label}
        <span className="flex flex-col leading-[0.5]">
          <span className={cn('text-[8px]', active && sortDir === 'asc' ? 'text-midas-red' : 'text-muted-foreground/35')}>▲</span>
          <span className={cn('text-[8px]', active && sortDir === 'desc' ? 'text-midas-red' : 'text-muted-foreground/35')}>▼</span>
        </span>
      </button>
    </th>
  )
}

// ── 分页控件 ──────────────────────────────────────────────────────────────
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
