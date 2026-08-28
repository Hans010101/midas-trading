'use client'

/**
 * 加密频道 · 列表页(币种列表 / 涨幅榜)· 接真实数据(M2-D)· 全域化(ADR-0018 后续)。
 *
 * 数据走 M2-A 已有的只读端点(lib/api/crypto-market.ts):
 *   · GET /api/v1/crypto/overview      → 合约总成交额 + 恐慌贪婪指数 + BTC/ETH 价
 *   · GET /api/v1/crypto/tickers/24h   → 全市场 USDT perp ticker(top=1000 一次取全量)
 *   · GET /api/v1/crypto/futures/metrics-batch → 资金费率/账户多空比/OI 24H变化(只对可见行分批取)
 *
 * 全域化(取代旧"前100 + 分页"):
 *   · 一次取全市场 USDT perp 进内存;排序/搜索基于全域。
 *   · 全域可排序列:24H 涨跌% / 24H 成交额 / 最新价(都在 ticker 表,前端内存排,即时)。
 *   · 资金费率/多空比/OI 3 列:只展示不排序(全域按这 3 列排序需单独后端工程,本期不做)。
 *   · metrics 受批量接口 200 上限约束 → 只对"已加载/可见行"分批请求(≤100/批 + inFlight 去重 +
 *     fetched 标记避免重复),滚动加载到哪就补取到哪。
 *
 * 红线 · 真实 vs 待补:交易对/价格/涨跌/高低/成交额 = 真实(ticker);资金费率/多空比/OI =
 *   USDT 永续采集范围内真实,范围外(USDC 本位等)或未采到一律「—」,绝不伪造。
 *
 * 交互:行点击 → 新标签打开 /crypto-preview?symbol=<BTCUSDT>。加密频道只展示合约榜(perp)。
 */

import { useEffect, useMemo, useRef, useState } from 'react'

import { BollScanList } from '@/components/crypto/boll-scan-list'
import { TopNav } from '@/components/layout/top-nav'
import { DataTimestamp } from '@/components/ui/state'
import { useIndicatorPrefs } from '@/hooks/use-indicator-prefs'
import {
  fetchCryptoOverview,
  fetchFuturesMetricsBatch,
  fetchTickers24h,
  FUTURES_METRICS_BATCH_LIMIT,
  type FuturesMetricItem,
} from '@/lib/api/crypto-market'
import { useQuery } from '@tanstack/react-query'
import { detailHref } from '@/lib/seo/detail-symbols'
import { cn } from '@/lib/utils'

const BOARD_SIZE = 100 // 榜单显示前 100(去无限滚动 · 更多币种走搜索 · 四市场统一)
// Cloudflare 独立 API 每次最多完整处理 15 个 symbol（15 × 2 条 analytics + 1 条共享
// ticker = 31 个上游子请求，低于 Free 的 50 上限）。必须按同一上限分批；旧版一次发送
// 100 个、API 静默截断到 15 个，却把后 85 个也标为 fetched，导致第 16 行起永久「—」。
const METRICS_CHUNK = FUTURES_METRICS_BATCH_LIMIT

// 全域可排序列(均为 ticker 表字段,前端内存排)
type SortKey = 'chgPct' | 'turnover' | 'price'

type FuturesMetric = Pick<
  FuturesMetricItem,
  'funding_rate' | 'account_long_short_ratio' | 'oi_change_pct_24h'
>

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

// 恐慌贪婪指数 状态值 英→中(今后统一中文)
const FGI_ZH: Record<string, string> = {
  'Extreme Fear': '极度恐惧',
  Fear: '恐惧',
  Neutral: '中性',
  Greed: '贪婪',
  'Extreme Greed': '极度贪婪',
}
function fgClassZh(c: string): string {
  return FGI_ZH[c] ?? c
}

export function CryptoMarketPage() {
  const [sortKey, setSortKey] = useState<SortKey>('chgPct')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [query, setQuery] = useState('')
  // 榜单切换:涨幅榜(默认 · 现状不变)⇄ 做T信号(读 A-1 快照)· 纯前端状态,不刷整页
  const [board, setBoard] = useState<'gainers' | 'boll'>('gainers')

  // ★做T信号暗发布:仅账号偏好 day_trade=ON 才显示「做T信号」榜单入口(#158 · 未登录/未开=隐藏)。
  //   未登录 → useIndicatorPrefs disabled → 无数据 → dayTradeEnabled=false → 切换器整体不渲染。
  const indicatorPrefsQ = useIndicatorPrefs()
  const dayTradeEnabled = indicatorPrefsQ.data?.day_trade === true
  // day_trade 关闭(或登出 · 或另一标签页改了偏好)时若正停在做T榜 → 回落涨幅榜。
  useEffect(() => {
    if (!dayTradeEnabled && board === 'boll') setBoard('gainers')
  }, [dayTradeEnabled, board])

  const overviewQ = useQuery({
    queryKey: ['crypto-overview'],
    queryFn: ({ signal }) => fetchCryptoOverview(signal),
    retry: 0,
    staleTime: 60_000,
  })

  // 全域:一次取全市场 perp(top=1000),进内存做排序/搜索
  const tickersQ = useQuery({
    queryKey: ['crypto-tickers', 'perp'],
    queryFn: ({ signal }) => fetchTickers24h('perp', 1000, signal),
    retry: 0,
    staleTime: 60_000,
  })

  // 整个加密频道只展示 USDT 本位永续 —— crypto_ticker_24h 是全市场(混入 USDC 本位、
  // BTC 计价如 ETHBTC、季度合约 BTCUSDT_260626 等)。这些采集层(ADR-0018 USDT-only)
  // 根本没采,其资金费率/多空比/OI 永远「—」,属无效行。用与采集一致的规则(symbol 以
  // '/USDT' 结尾,即 quote=USDT)过滤,使列表/排序/无限滚动/搜索全部只在 USDT 本位范围内。
  const allItems = useMemo(
    () => (tickersQ.data?.items ?? []).filter((it) => it.symbol.endsWith('/USDT')),
    [tickersQ.data],
  )

  // ── 搜索(全域前端过滤)+ 排序(全域前端,仅 ticker 三列)──────────────────
  const viewRows = useMemo(() => {
    const q = query.trim().toUpperCase()
    const filtered = q ? allItems.filter((it) => it.symbol.toUpperCase().includes(q)) : allItems
    const get = (it: (typeof allItems)[number]) =>
      sortKey === 'chgPct' ? it.change_pct_24h
        : sortKey === 'turnover' ? it.quote_volume_24h
          : it.last_price
    const dir = sortDir === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => (get(a) - get(b)) * dir)
  }, [allItems, query, sortKey, sortDir])

  // 榜单显示前 100(去无限滚动)· 搜索仍覆盖全域 viewRows(全市场 ~623),只是显示截断前 100
  const visibleRows = useMemo(() => viewRows.slice(0, BOARD_SIZE), [viewRows])

  // 排序/搜索变化 → 滚回顶部
  useEffect(() => {
    if (typeof window !== 'undefined') window.scrollTo({ top: 0 })
  }, [sortKey, sortDir, query])

  // ── 累积式分批 metrics(只对可见行,避开 200 上限)──────────────────────────
  const [metricsMap, setMetricsMap] = useState<Map<string, FuturesMetric>>(new Map())
  const fetchedRef = useRef<Set<string>>(new Set()) // 已请求过(含无数据)· 不再重复请求
  const inFlightRef = useRef<Set<string>>(new Set()) // 在途 · 防滚动抖动重复请求

  // 注意:这里【不】用 cancelled 标志取消在飞批次。metricsMap 是按 symbol 幂等累积的,
  // 取消批次只会丢结果、不会带来正确性收益。曾因「在飞批次被 visibleRows 抖动取代 → 早退
  // 丢结果 + inFlight 去重挡住补发」导致首屏前 20 行资金费率/多空比/OI 永久空(生产复现)。
  // 修法:① 发请求时就乐观标 fetched(被取代也不悬空、不重复请求)· ② 返回一律 merge ·
  //       ③ 仅失败时回滚 fetched 以便重试。
  useEffect(() => {
    const want = visibleRows
      .map((r) => toBinanceSymbol(r.symbol))
      .filter((s) => !fetchedRef.current.has(s) && !inFlightRef.current.has(s))
    if (want.length === 0) return

    for (let i = 0; i < want.length; i += METRICS_CHUNK) {
      const chunk = want.slice(i, i + METRICS_CHUNK)
      // 乐观标记:发请求时就标 fetched + inFlight。即使本轮 effect 随后被 visibleRows 抖动
      // (无限滚动 20→40 / 切排序搜索)取代,这批 symbol 也不会悬空、不会被重复请求。
      chunk.forEach((s) => { fetchedRef.current.add(s); inFlightRef.current.add(s) })
      fetchFuturesMetricsBatch(chunk)
        .then((res) => {
          // 按 symbol 幂等 merge —— 不因 effect 被取代而丢结果(前 20 行空 bug 的根因修复)。
          // 返回里没有的 symbol 保持「—」(采集范围外),已乐观标 fetched 不再重复请求。
          setMetricsMap((prev) => {
            const next = new Map(prev)
            for (const it of res.items) {
              next.set(it.symbol, {
                funding_rate: it.funding_rate,
                account_long_short_ratio: it.account_long_short_ratio,
                oi_change_pct_24h: it.oi_change_pct_24h,
              })
            }
            return next
          })
        })
        .catch(() => { chunk.forEach((s) => fetchedRef.current.delete(s)) }) // 失败回滚 fetched · 下次滚动可重试
        .finally(() => { chunk.forEach((s) => inFlightRef.current.delete(s)) })
    }
  }, [visibleRows])

  // ── 指标卡 ────────────────────────────────────────────────────────────────
  const ov = overviewQ.data?.market_overview
  const btc = overviewQ.data?.btc_ticker ?? null
  const eth = overviewQ.data?.eth_ticker ?? null
  const fgiOk = !!ov && ov.fear_greed_value > 0 && ov.fear_greed_classification !== '' && ov.fear_greed_classification !== 'N/A'
  const derivativesSource = ov?.derivatives_source === 'bybit_futures'
    ? 'Bybit USDT 永续'
    : ov?.derivatives_source === 'kraken_futures'
      ? 'Kraken USD 永续'
      : '暂无数据'

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('desc') }
  }
  function openDetail(ccxtSymbol: string) {
    window.open(
      detailHref({ symbol: toBinanceSymbol(ccxtSymbol), market: 'crypto' }),
      '_blank',
      'noopener,noreferrer',
    )
  }

  const fmtPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />

      <main className="flex-1">
        <div className="mx-auto max-w-[1600px] px-3 py-4 sm:px-6 sm:py-5">
          {/* H1「加密市场」已删 · 顶部市场切换 Tab 已有「加密」· 标题冗余。 */}
          {/* 顶部 4 指标卡 */}
          <div className="mb-5 grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
            <MetricCard
              label="24H 合约总成交额"
              loading={overviewQ.isPending}
              value={ov && ov.derivatives_volume_24h_usd > 0 ? fmtUsd(ov.derivatives_volume_24h_usd) : '—'}
              sub={derivativesSource}
            />
            <MetricCard
              label="恐慌贪婪指数"
              loading={overviewQ.isPending}
              value={fgiOk ? String(ov!.fear_greed_value) : '—'}
              sub={fgiOk ? fgClassZh(ov!.fear_greed_classification) : '暂无数据'}
              tone="bull"
            />
            <MetricCard
              label="BTC 价格"
              loading={overviewQ.isPending}
              value={btc ? `$${fmtPrice(btc.last_price)}` : '—'}
              sub={btc ? fmtPct(btc.change_pct_24h) : '暂无数据'}
              tone={btc ? (btc.change_pct_24h >= 0 ? 'bull' : 'bear') : undefined}
            />
            <MetricCard
              label="ETH 价格"
              loading={overviewQ.isPending}
              value={eth ? `$${fmtPrice(eth.last_price)}` : '—'}
              sub={eth ? fmtPct(eth.change_pct_24h) : '暂无数据'}
              tone={eth ? (eth.change_pct_24h >= 0 ? 'bull' : 'bear') : undefined}
            />
          </div>

          {/* 工具条:榜单切换器 + (仅涨幅榜)搜索/刷新 */}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            {/* ★切换器:合约 24H 涨幅榜 ⇄ 做T信号 · 做T信号仅暗发布(day_trade=ON)用户可见,
                未开启则整个切换器不渲染(只见涨幅榜 · 现状不变)· 默认涨幅榜 · 前端状态不刷整页 */}
            <div className="flex items-center gap-3">
              {dayTradeEnabled && (
              <div className="inline-flex rounded-lg border border-paper bg-surface-card p-0.5">
                <button type="button" onClick={() => setBoard('gainers')}
                  className={cn('rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    board === 'gainers' ? 'bg-midas-red text-white shadow-sm' : 'text-muted-foreground hover:text-midas-red')}>
                  合约 24H 涨幅榜
                </button>
                <button type="button" onClick={() => setBoard('boll')}
                  className={cn('rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    board === 'boll' ? 'bg-midas-red text-white shadow-sm' : 'text-muted-foreground hover:text-midas-red')}>
                  做T信号
                </button>
              </div>
              )}
              <DataTimestamp value={tickersQ.data?.items[0]?.ts ?? ov?.ts} />
            </div>

            {board === 'gainers' && (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-md border border-paper bg-surface-card px-3 py-1.5 text-sm">
                <SearchIcon />
                <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
                  placeholder={`搜索 ${allItems.length || '全市场'} 个 USDT 永续`}
                  className="w-44 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50" />
              </div>
              <button type="button" title="刷新" onClick={() => { void overviewQ.refetch(); void tickersQ.refetch() }}
                className="flex items-center gap-1.5 rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-midas-red hover:text-midas-red">
                <RefreshIcon />刷新
              </button>
            </div>
            )}
          </div>

          {/* 榜单表格(★board==='gainers' 守卫包裹 · 涨幅榜原逻辑零改,仅被切换控制显隐)*/}
          {board === 'gainers' && (
          <div className="overflow-x-auto rounded-lg border border-paper">
            <table className="w-full min-w-[1100px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-paper bg-surface-card text-xs text-muted-foreground">
                  <th className="w-12 px-3 py-2 text-center font-medium">#</th>
                  <th className="px-3 py-2 text-left font-medium">交易对</th>
                  <SortTh label="最新价格" col="price" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <SortTh label="24H 涨跌%" col="chgPct" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <th className="px-3 py-2 text-right font-medium">24H 最高</th>
                  <th className="px-3 py-2 text-right font-medium">24H 最低</th>
                  <th className="px-3 py-2 text-right font-medium" title="合约 · USDT 永续采集范围内真实,范围外/未采到「—」">资金费率</th>
                  <th className="px-3 py-2 text-right font-medium" title="合约 · 账户多空比 long/short">账户多空比</th>
                  <th className="px-3 py-2 text-right font-medium" title="合约 · OI 近 24H 变化%">OI 24H 变化</th>
                  <SortTh label="24H 成交额" col="turnover" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {tickersQ.isPending && <StateRow text="载入中…" />}
                {tickersQ.isError && <StateRow text="暂时无法读取行情(后端不可达)" />}
                {tickersQ.isSuccess && viewRows.length === 0 && (
                  <StateRow text={query ? '无匹配交易对' : '暂无行情数据 · 待采集'} />
                )}
                {tickersQ.isSuccess && visibleRows.map((r, i) => {
                  const fm = metricsMap.get(toBinanceSymbol(r.symbol))
                  const fr = fm?.funding_rate
                  const ls = fm?.account_long_short_ratio
                  const oi = fm?.oi_change_pct_24h
                  return (
                    <tr key={r.symbol} onClick={() => openDetail(r.symbol)} title="点击在新标签打开详情页"
                      className="group cursor-pointer border-b border-paper/60 transition-colors hover:bg-midas-red-glow/30">
                      <td className="px-3 py-2.5 text-center font-mono text-xs text-muted-foreground/70">{i + 1}</td>
                      <td className="px-3 py-2.5"><span className="font-serif font-bold text-foreground">{r.symbol}</span></td>
                      <Td>{fmtPrice(r.last_price)}</Td>
                      <Td className={r.change_pct_24h >= 0 ? 'text-up' : 'text-down'}>{fmtPct(r.change_pct_24h)}</Td>
                      <Td className="text-muted-foreground/80">{fmtPrice(r.high_24h)}</Td>
                      <Td className="text-muted-foreground/80">{fmtPrice(r.low_24h)}</Td>
                      <Td className={fr == null ? 'text-muted-foreground/40' : fr >= 0 ? 'text-up' : 'text-down'}>
                        {fr == null ? '—' : `${fr >= 0 ? '+' : ''}${(fr * 100).toFixed(4)}%`}
                      </Td>
                      <Td className={ls == null ? 'text-muted-foreground/40' : 'text-muted-foreground/80'}>
                        {ls == null ? '—' : ls.toFixed(2)}
                      </Td>
                      <Td className={oi == null ? 'text-muted-foreground/40' : oi >= 0 ? 'text-up' : 'text-down'}>
                        {oi == null ? '—' : `${oi >= 0 ? '+' : ''}${oi.toFixed(2)}%`}
                      </Td>
                      <Td className="text-muted-foreground/80">{fmtUsd(r.quote_volume_24h)}</Td>
                      <td className="px-2 text-center text-muted-foreground/30 transition-colors group-hover:text-midas-red">›</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          )}

          {/* 底部一行(榜单显示前 100 · 更多请搜索 · 居中 · 四市场统一)*/}
          {board === 'gainers' && (
          <p className="mt-4 text-center text-xs text-muted-foreground/70">
            {query.trim()
              ? `命中 ${viewRows.length} 个 · 显示前 ${Math.min(BOARD_SIZE, viewRows.length)}`
              : '榜单显示前 100 · 更多请搜索查询'}
          </p>
          )}

          {/* ── 做T信号列表(board==='boll' · 读 A-1 /crypto/boll-scan 快照)── */}
          {board === 'boll' && <BollScanList onSymbolClick={openDetail} />}
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
      <div className={cn('mt-1 font-mono text-2xl font-bold', tone === 'bull' ? 'text-up' : tone === 'bear' ? 'text-down' : 'text-foreground')}>
        {loading ? '…' : value}
      </div>
      {sub && <div className={cn('mt-0.5 text-[11px]', tone === 'bull' ? 'text-up' : tone === 'bear' ? 'text-down' : 'text-muted-foreground/70')}>{loading ? '' : sub}</div>}
    </div>
  )
}

// ── 可排序表头(全域 · 仅 ticker 三列)────────────────────────────────────────
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
