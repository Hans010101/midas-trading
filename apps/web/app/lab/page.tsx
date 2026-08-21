'use client'

/**
 * 策略研究室 · 回测列表 + 发起(P1-4d · ADR 0038)。
 *
 * 骨架照 app/crypto-market/page.tsx:'use client' + TopNav + main 容器 + 行内状态机。
 * 🔴 红线:回测纯虚拟研究 · market 锁 crypto perp(不可改)· 绝不下单 / 撮合 / 真实交易。
 * ⛔ 隐藏路由:不挂全局导航,内部可见。
 */

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useState, type ReactNode } from 'react'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { LabNav } from '@/components/lab/lab-nav'
import { TopNav } from '@/components/layout/top-nav'
import { Button } from '@/components/ui/button'
import { QuotaHint } from '@/components/quota/quota-hint'
import { useInvalidateQuota, useQuota } from '@/hooks/use-quota'
import { useRuntimeDocumentTitle } from '@/hooks/use-runtime-document-title'
import { BacktestApiError } from '@/lib/api/backtest'
import { isExhausted, parseQuotaDetail, quotaErrorMessage, quotaItemFor } from '@/lib/quota-view'
import { Input } from '@/components/ui/input'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { useBacktestList, useCreateBacktest } from '@/hooks/use-backtest'
import type { BacktestStatus, BacktestStrategy } from '@/lib/api/backtest'
import { cn } from '@/lib/utils'

const STATUS_LABEL: Record<BacktestStatus, { zh: string; en: string }> = {
  pending: { zh: '进行中', en: 'Running' },
  done: { zh: '完成', en: 'Completed' },
  error: { zh: '失败', en: 'Failed' },
}

const PAGE_SIZE = 10 // 列表每页条数(纯前端切片分页 · 后端 limit 50 已够覆盖,不碰后端)

// P2-period:放开 1h + 1d 两档(15m 数据太浅不放 · 后端 schema 虽允许但前端不给选项)。
// 控件范式照 crypto-header.tsx 周期切换器;1h 年化基数由后端 bars_per_year 补丁保证(同刀)。
const LAB_PERIODS = [
  { value: '1h', zh: '1h', en: '1h' },
  { value: '1d', zh: '1d · 日线', en: '1d · Daily' },
] as const
type LabPeriod = (typeof LAB_PERIODS)[number]['value']
const LAB_STRATEGIES: Array<{ value: BacktestStrategy; zh: string; en: string }> = [
  { value: 'sma_cross', zh: '双均线交叉', en: 'SMA crossover' },
  { value: 'macd_cross', zh: 'MACD 交叉', en: 'MACD crossover' },
  { value: 'rsi_reversal', zh: 'RSI 反转', en: 'RSI reversal' },
  { value: 'boll_reversion', zh: '布林回归', en: 'Bollinger reversion' },
  { value: 'kdj_cross', zh: 'KDJ 交叉', en: 'KDJ crossover' },
]

export default function LabPage() {
  const { locale } = useRuntimeLocale()
  useRuntimeDocumentTitle({
    locale,
    english: 'Strategy Backtest',
    chinese: '策略研究室',
  })
  const router = useRouter()
  const { status: authStatus } = useSession()
  const list = useBacktestList()
  const create = useCreateBacktest()
  // 会员刀2:额度展示(剩 M 次 / 耗尽置灰)· 发起后刷新计数
  const quota = useQuota()
  const invalidateQuota = useInvalidateQuota()
  const backtestQuota = quotaItemFor(quota.data, 'backtest')
  const exhausted = backtestQuota !== null && isExhausted(backtestQuota)

  const [symbol, setSymbol] = useState('BTCUSDT')
  const [strategy, setStrategy] = useState<BacktestStrategy>('sma_cross')
  const [start, setStart] = useState('2025-01-17')
  const [end, setEnd] = useState('2026-05-31')
  const [smaFast, setSmaFast] = useState(5)
  const [smaSlow, setSmaSlow] = useState(20)
  const [commissionRate, setCommissionRate] = useState(0.0005)
  const [slippageBps, setSlippageBps] = useState(5)
  const [period, setPeriod] = useState<LabPeriod>('1d')
  const [page, setPage] = useState(1)

  // 前端切片分页(数据已由 useBacktestList 一次取回 ≤50 条)· currentPage 夹取防越界
  const rows = list.data ?? []
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageRows = rows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  function submit() {
    create.mutate(
      {
        symbol: symbol.trim().toUpperCase(),
        start,
        end,
        market: 'crypto', // 红线:锁 crypto perp,不从表单取
        period, // P2-period:1h / 1d 从段控件取(LabPeriod 仅两档)
        strategy,
        sma_fast: smaFast,
        sma_slow: smaSlow,
        commission_rate: commissionRate,
        slippage_bps: slippageBps,
      },
      {
        onSuccess: (data) => router.push(`/lab/report?id=${data.id}`),
        onSettled: invalidateQuota,
      },
    )
  }

  // 429(额度耗尽)→ 结构化 detail 友好文案;其余错误原样(会员刀2)
  function createErrorText(err: Error): string {
    if (err instanceof BacktestApiError && err.status === 429) {
      const d = parseQuotaDetail(err.rawDetail)
      if (d) return quotaErrorMessage(d, locale)
    }
    return err.message
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="mx-auto w-full max-w-5xl px-6 py-8">
        {/* 大标题已删(同 assistant 页口径):TopNav 高亮 + LabNav 已标位,重复是噪声 */}
        <LabNav />

        {authStatus === 'unauthenticated' ? (
          <EmptyState
            title={locale === 'en' ? 'Sign in to continue' : '请先登录'}
            hint={
              locale === 'en'
                ? 'Strategy backtests are available to registered users'
                : '研究室回测需要登录后访问'
            }
          />
        ) : (
          <>
            {/* ── 发起表单 ──────────────────────────────────────────── */}
            <section className="mb-10 rounded-lg border border-paper bg-cream p-5 shadow-sm">
              <h2 className="mb-4 font-serif text-lg font-bold">
                {locale === 'en' ? 'Run a backtest' : '发起回测'}
              </h2>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <Field label={locale === 'en' ? 'Strategy' : '策略'}>
                  <select
                    value={strategy}
                    onChange={(event) => setStrategy(event.target.value as BacktestStrategy)}
                    className="h-10 w-full rounded-md border border-paper bg-background px-3 text-sm"
                  >
                    {LAB_STRATEGIES.map((item) => (
                      <option key={item.value} value={item.value}>{item[locale]}</option>
                    ))}
                  </select>
                </Field>
                <Field label={locale === 'en' ? 'Instrument (crypto perpetual)' : '标的(crypto perp)'}>
                  <Input
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    placeholder="BTCUSDT"
                  />
                </Field>
                <Field label={locale === 'en' ? 'Market (fixed)' : '市场(锁定)'}>
                  <Input
                    value="crypto perp"
                    disabled
                    readOnly
                    className="cursor-not-allowed bg-surface-subtle text-muted-foreground"
                  />
                </Field>
                <Field label={locale === 'en' ? 'Timeframe' : '周期'}>
                  <div className="flex h-10 items-center gap-1">
                    {LAB_PERIODS.map((p) => (
                      <button
                        key={p.value}
                        type="button"
                        onClick={() => setPeriod(p.value)}
                        className={cn(
                          'rounded px-2 py-1 text-sm transition-colors',
                          p.value === period
                            ? 'bg-midas-red-glow text-midas-red'
                            : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                          {p[locale]}
                      </button>
                    ))}
                  </div>
                  {period === '1h' && (
                    <p className="mt-1 text-xs text-faint">
                      {locale === 'en'
                        ? 'Hourly data begins on May 8, 2026. Earlier start dates will return no data.'
                        : '1h 数据自 2026-05-08 起,选更早的开始日期将提示查无数据'}
                    </p>
                  )}
                </Field>
                <Field label={locale === 'en' ? 'Start date' : '开始日期'}>
                  <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
                </Field>
                <Field label={locale === 'en' ? 'End date' : '结束日期'}>
                  <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
                </Field>
                {strategy === 'sma_cross' && <div className="grid grid-cols-2 gap-3">
                  <Field label={locale === 'en' ? 'Fast SMA' : 'SMA 快线'}>
                    <Input
                      type="number"
                      min={1}
                      value={smaFast}
                      onChange={(e) => setSmaFast(Number(e.target.value))}
                    />
                  </Field>
                  <Field label={locale === 'en' ? 'Slow SMA' : 'SMA 慢线'}>
                    <Input
                      type="number"
                      min={1}
                      value={smaSlow}
                      onChange={(e) => setSmaSlow(Number(e.target.value))}
                    />
                  </Field>
                </div>}
                <div className="grid grid-cols-2 gap-3">
                  <Field label={locale === 'en' ? 'Commission rate' : '手续费率'}>
                    <Input
                      type="number"
                      min={0}
                      max={0.02}
                      step={0.0001}
                      value={commissionRate}
                      onChange={(e) => setCommissionRate(Number(e.target.value))}
                    />
                  </Field>
                  <Field label={locale === 'en' ? 'Slippage (bps)' : '滑点（bps）'}>
                    <Input
                      type="number"
                      min={0}
                      max={200}
                      value={slippageBps}
                      onChange={(e) => setSlippageBps(Number(e.target.value))}
                    />
                  </Field>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <Button
                  onClick={submit}
                  disabled={create.isPending || exhausted || symbol.trim() === ''}
                >
                  {create.isPending
                    ? locale === 'en' ? 'Starting…' : '发起中…'
                    : locale === 'en' ? 'Run backtest' : '发起回测'}
                </Button>
                {/* 额度提示(剩 M 次 / 耗尽引导官网会员区)· 如实展示 */}
                <QuotaHint item={backtestQuota} locale={locale} />
                {create.isError && (
                  <span className="text-sm text-midas-red">{createErrorText(create.error)}</span>
                )}
              </div>
              <p className="mt-3 text-xs text-faint">
                {locale === 'en'
                  ? 'Five deterministic strategies with configurable commission and slippage.'
                  : '五种确定性策略，手续费和滑点均可配置并计入收益。'}
              </p>
            </section>

            {/* ── 我的回测列表 ──────────────────────────────────────── */}
            <section>
              <h2 className="mb-3 font-serif text-lg font-bold">
                {locale === 'en' ? 'My backtests' : '我的回测'}
              </h2>
              {list.isPending ? (
                <LoadingNote className="py-12" />
              ) : list.isError ? (
                <EmptyState
                  title={locale === 'en' ? 'Backtests are temporarily unavailable' : '暂时无法读取'}
                  hint={locale === 'en' ? 'Try again shortly' : '后端不可达 · 稍后重试'}
                />
              ) : rows.length === 0 ? (
                <EmptyState
                  icon="🧪"
                  title={locale === 'en' ? 'No backtests yet' : '还没有回测'}
                  hint={locale === 'en' ? 'Use the form above to run your first test' : '用上方表单发起第一个'}
                />
              ) : (
                <>
                  <div className="overflow-x-auto rounded-lg border border-paper">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-paper bg-surface-card text-xs text-muted-foreground">
                          <th className="px-3 py-2 text-left font-medium">#</th>
                          <th className="px-3 py-2 text-left font-medium">
                            {locale === 'en' ? 'Instrument' : '标的'}
                          </th>
                          <th className="px-3 py-2 text-left font-medium">
                            {locale === 'en' ? 'Strategy' : '策略'}
                          </th>
                          <th className="px-3 py-2 text-left font-medium">
                            {locale === 'en' ? 'Period' : '区间'}
                          </th>
                          <th className="px-3 py-2 text-left font-medium">
                            {locale === 'en' ? 'Status' : '状态'}
                          </th>
                          <th className="px-3 py-2 text-left font-medium">
                            {locale === 'en' ? 'Created' : '创建时间'}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {pageRows.map((r) => (
                          <tr
                            key={r.id}
                            onClick={() => router.push(`/lab/report?id=${r.id}`)}
                            className="cursor-pointer border-b border-paper/60 transition-colors hover:bg-midas-red-glow/30"
                          >
                            <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground/70">
                              {r.id}
                            </td>
                            <td className="px-3 py-2.5 font-mono font-bold">{r.symbol}</td>
                            <td className="px-3 py-2.5 text-xs text-muted-foreground">
                              {LAB_STRATEGIES.find((item) => item.value === r.strategy)?.[locale] ?? r.strategy}
                            </td>
                            <td className="px-3 py-2.5 text-xs text-muted-foreground">
                              {r.start_date} → {r.end_date}
                            </td>
                            <td className="px-3 py-2.5">
                              <StatusBadge status={r.status} locale={locale} />
                            </td>
                            <td className="px-3 py-2.5 text-xs text-muted-foreground">
                              {new Date(r.created_at).toLocaleString(
                                locale === 'en' ? 'en-US' : 'zh-CN',
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {totalPages > 1 && (
                    <div className="mt-4 flex items-center justify-center gap-4">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={currentPage <= 1}
                        onClick={() => setPage(currentPage - 1)}
                      >
                        {locale === 'en' ? 'Previous' : '上一页'}
                      </Button>
                      <span className="font-mono text-xs text-muted-foreground">
                        {locale === 'en'
                          ? `Page ${currentPage} of ${totalPages}`
                          : `第 ${currentPage} / ${totalPages} 页`}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={currentPage >= totalPages}
                        onClick={() => setPage(currentPage + 1)}
                      >
                        {locale === 'en' ? 'Next' : '下一页'}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

function StatusBadge({
  status,
  locale,
}: {
  status: BacktestStatus
  locale: 'en' | 'zh'
}) {
  const cls =
    status === 'done'
      ? 'bg-success/10 text-success'
      : status === 'error'
        ? 'bg-midas-red/10 text-midas-red'
        : 'bg-gold/15 text-gold'
  return (
    <span className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${cls}`}>
      {STATUS_LABEL[status][locale]}
    </span>
  )
}
