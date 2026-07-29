'use client'

/**
 * 研究室回测报告 · B 档(取数自渲染 · Midas 设计语言)· P1-4d(ADR 0038 D4)。
 *
 * 结构照 components/crypto-preview/crypto-detail.tsx:'use client' + useSearchParams 读 ?id=。
 * 曲线照 account EquityCurveCard(单线)+ dimension OiChart(双线):equity 红实线 + benchmark 灰虚线。
 *
 * 🔴 红线:纯虚拟研究展示 · 绝不下单 / 撮合 / 真实交易。
 *    研究页不挂 VIRTUAL 徽章 / 免责(Hans 授权去除 · 与「虚拟下单 UI」红线区分,后者徽章/免责保留)。
 */

import { useSession } from 'next-auth/react'
import { useSearchParams } from 'next/navigation'
import type { ReactNode } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { TopNav } from '@/components/layout/top-nav'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { useBacktestRun } from '@/hooks/use-backtest'
import { useRuntimeDocumentTitle } from '@/hooks/use-runtime-document-title'
import type { BacktestMetrics, BacktestRunResponse, Trade } from '@/lib/api/backtest'
// 格式化函数已抽到 lib/format-backtest.ts(量纲契约唯一实现 + vitest 锁死 · ADR 0040)。
// 选用规则:比率→fmtPct(×100)· 百分比数值→fmtPctNum(仅 return_pct)· 详见该文件头注释。
import { fmtInt, fmtNum, fmtPct, fmtPctNum, fmtRatio } from '@/lib/format-backtest'

// ── 16 指标卡定义(tone:true → 按正负染 涨/跌 色)──────────────────────────────
type MetricKey = keyof BacktestMetrics
interface MetricDef {
  key: MetricKey
  zh: string
  en: string
  fmt: (v: number) => string
  tone?: boolean
  subZh?: string
  subEn?: string
}
const METRIC_DEFS: MetricDef[] = [
  { key: 'total_return', zh: '总收益率', en: 'Total return', fmt: fmtPct, tone: true },
  { key: 'annual_return', zh: '年化收益', en: 'Annualized return', fmt: fmtPct, tone: true },
  { key: 'max_drawdown', zh: '最大回撤', en: 'Max drawdown', fmt: fmtPct },
  { key: 'sharpe', zh: '夏普比率', en: 'Sharpe ratio', fmt: fmtRatio, tone: true },
  { key: 'sortino', zh: '索提诺比率', en: 'Sortino ratio', fmt: fmtRatio, tone: true },
  { key: 'calmar', zh: '卡玛比率', en: 'Calmar ratio', fmt: fmtRatio, tone: true },
  { key: 'win_rate', zh: '胜率', en: 'Win rate', fmt: fmtPct },
  { key: 'profit_loss_ratio', zh: '盈亏比', en: 'Profit / loss ratio', fmt: fmtRatio },
  { key: 'profit_factor', zh: '盈利因子', en: 'Profit factor', fmt: fmtRatio },
  {
    key: 'trade_count',
    zh: '交易笔数',
    en: 'Completed trades',
    fmt: fmtInt,
    subZh: '完整回合(开+平)',
    subEn: 'Entry + exit',
  },
  { key: 'max_consecutive_loss', zh: '最大连亏', en: 'Max losing streak', fmt: fmtInt },
  { key: 'avg_holding_days', zh: '平均持仓(天)', en: 'Avg. holding days', fmt: (v) => v.toFixed(1) },
  { key: 'benchmark_return', zh: '基准收益', en: 'Benchmark return', fmt: fmtPct, tone: true },
  { key: 'excess_return', zh: '超额收益', en: 'Excess return', fmt: fmtPct, tone: true },
  { key: 'information_ratio', zh: '信息比率', en: 'Information ratio', fmt: fmtRatio, tone: true },
  { key: 'final_value', zh: '期末权益', en: 'Ending equity', fmt: fmtNum },
]

export function LabReport() {
  const { locale } = useRuntimeLocale()
  useRuntimeDocumentTitle({
    locale,
    english: 'Backtest Report',
    chinese: '回测报告',
  })
  const searchParams = useSearchParams()
  const { status: authStatus } = useSession()
  const idParam = searchParams.get('id')
  const id = idParam && /^\d+$/.test(idParam) ? Number(idParam) : null

  const { data: run, isPending, isError, error } = useBacktestRun(id)

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="mx-auto w-full max-w-5xl px-6 py-8">
        {authStatus === 'unauthenticated' ? (
          <EmptyState
            title={locale === 'en' ? 'Sign in to continue' : '请先登录'}
            hint={locale === 'en' ? 'Backtest reports are available to registered users' : '研究室回测需要登录后访问'}
          />
        ) : id == null ? (
          <EmptyState
            title={locale === 'en' ? 'Backtest ID is missing' : '缺少回测 id'}
            hint={locale === 'en' ? 'Open a report from the backtest list' : '请从研究室列表进入'}
          />
        ) : isError ? (
          <ErrorBox text={error?.message ?? (locale === 'en' ? 'Unable to load the report' : '读取失败')} />
        ) : isPending || !run ? (
          <LoadingNote className="py-16" />
        ) : run.status === 'pending' ? (
          <LoadingNote className="py-16">
            {locale === 'en' ? 'Backtest running… Auto-refresh is on.' : '回测进行中…(自动刷新)'}
          </LoadingNote>
        ) : run.status === 'error' ? (
          <ErrorBox
            text={
              locale === 'en'
                ? `Backtest failed: ${run.error ?? 'Unknown error'}`
                : `回测失败:${run.error ?? '未知错误'}`
            }
          />
        ) : (
          <ReportBody run={run} locale={locale} />
        )}
      </main>
    </div>
  )
}

// ── done 报告主体 ────────────────────────────────────────────────────────────
function ReportBody({
  run,
  locale,
}: {
  run: BacktestRunResponse
  locale: 'en' | 'zh'
}) {
  const m = run.metrics_json
  const equity = run.equity_json ?? []
  const trades = run.trades_json ?? []
  // 回撤副图数据 · 防御式:drawdown 符号/量纲未实测确认 → Math.abs 统一成「回撤深度」正值;
  //   raw 保留原值供 tooltip 真机核对量纲(若实际是正比率,Math.abs 不改值;若是负比率,翻正显示)。
  const drawdownData = equity.map((p) => ({
    timestamp: p.timestamp,
    dd: Math.abs(p.drawdown ?? 0),
    raw: p.drawdown,
  }))

  return (
    <div className="space-y-8">
      {/* (a) 结论先行 + 标的/区间 */}
      <section>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h1 className="font-serif text-2xl font-bold">
            {locale === 'en' ? 'Backtest report' : '回测报告'}
          </h1>
        </div>
        <p className="font-mono text-sm text-muted-foreground">
          {run.symbol} · crypto perp · {run.period} · {run.start_date} → {run.end_date}
        </p>
        {m && (
          <div className="mt-3 rounded-lg border border-paper bg-cream p-4 shadow-sm">
            <p className="text-sm leading-relaxed text-foreground">
              {conclusion(run.symbol, m, locale)}
            </p>
          </div>
        )}
      </section>

      {/* (b) 16 指标卡 */}
      {m && (
        <section>
          <h2 className="mb-3 font-serif text-lg font-bold">
            {locale === 'en' ? 'Key metrics' : '关键指标'}
          </h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {METRIC_DEFS.map((d) => {
              const v = m[d.key]
              const toneCls = d.tone
                ? v > 0
                  ? 'text-up'
                  : v < 0
                    ? 'text-down'
                    : 'text-foreground'
                : 'text-foreground'
              return (
                <div
                  key={d.key}
                  className="rounded-lg border border-paper bg-cream p-4 shadow-sm"
                >
                  <div className="text-xs text-muted-foreground">
                    {locale === 'en' ? d.en : d.zh}
                  </div>
                  <div className={`mt-1 font-mono text-xl font-bold tabular-nums ${toneCls}`}>
                    {d.fmt(v)}
                  </div>
                  {(d.subZh || d.subEn) && (
                    <div className="mt-0.5 text-[10px] text-faint">
                      {locale === 'en' ? d.subEn : d.subZh}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {/* P2-period 收尾:日内周期的年化夏普类指标统计学 caveat(诊断结论:非 bug ·
              收益非 i.i.d. 时 ×√bars_per_year 放大且跨频率不可比 · Lo 2002)· 1d 不显示。 */}
          {run.period !== '1d' && (
            <p className="mt-2 text-xs text-faint">
              {locale === 'en'
                ? 'Hourly Sharpe, Sortino and information ratios assume independent returns and may be inflated for trend strategies. Do not compare them directly with daily tests; prioritize total return and max drawdown.'
                : '注:小时级回测的年化夏普/索提诺/信息比率按收益独立假设计算,趋势策略下会被放大,且不宜与日线策略直接比较;评估小时级策略请优先参考总收益与最大回撤。'}
            </p>
          )}
        </section>
      )}

      {/* (c) 双线收益曲线:策略 #C8102E 实线 + 基准 #94949C 虚线 */}
      <section>
        <h2 className="mb-3 font-serif text-lg font-bold">
          {locale === 'en' ? 'Equity curve' : '收益曲线'}
        </h2>
        <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
          {equity.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-sm text-faint">
              {locale === 'en' ? 'No equity-curve data' : '暂无曲线数据'}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={equity} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F7F6F1" />
                <XAxis
                  dataKey="timestamp"
                  fontSize={10}
                  tick={{ fill: '#94949C' }}
                  minTickGap={48}
                  tickLine={false}
                />
                <YAxis
                  fontSize={10}
                  tick={{ fill: '#94949C' }}
                  width={56}
                  domain={['auto', 'auto']}
                  tickFormatter={(v) => Number(v).toLocaleString()}
                />
                <Tooltip
                  contentStyle={{ background: '#FCFCF9', border: '1px solid #C8102E', fontSize: 12 }}
                  labelStyle={{ color: '#1A1A1A' }}
                  formatter={(v) => Number(v).toLocaleString()}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} iconSize={10} />
                <Line
                  type="monotone"
                  dataKey="equity"
                  name={locale === 'en' ? 'Strategy' : '策略'}
                  stroke="#C8102E"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark_equity"
                  name={locale === 'en' ? 'Benchmark (buy and hold)' : '基准(买入持有)'}
                  stroke="#94949C"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 回撤副图 · 防御式(Math.abs 统一回撤深度正值 · Y 轴 reversed 使「更深」向下)·
            tooltip 带原值供真机核对量纲 · 回撤用中国红系(负面) */}
        <div className="mt-4 rounded-lg border border-paper bg-cream p-4 shadow-sm">
          <h3 className="mb-2 font-serif text-sm font-bold">
            {locale === 'en' ? 'Drawdown' : '回撤'}
          </h3>
          {equity.length === 0 ? (
            <div className="flex h-24 items-center justify-center text-sm text-faint">
              {locale === 'en' ? 'No drawdown data' : '暂无回撤数据'}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={120}>
              <AreaChart data={drawdownData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F7F6F1" />
                <XAxis
                  dataKey="timestamp"
                  fontSize={10}
                  tick={{ fill: '#94949C' }}
                  minTickGap={48}
                  tickLine={false}
                />
                <YAxis
                  fontSize={10}
                  tick={{ fill: '#94949C' }}
                  width={56}
                  reversed
                  domain={[0, 'auto']}
                  tickFormatter={(v) => `${(Number(v) * 100).toFixed(1)}%`}
                />
                <Tooltip
                  contentStyle={{ background: '#FCFCF9', border: '1px solid #C8102E', fontSize: 12 }}
                  labelStyle={{ color: '#1A1A1A' }}
                  labelFormatter={(label, payload) => {
                    const raw = payload?.[0]?.payload?.raw
                    return `${label}${raw != null ? ` · ${locale === 'en' ? 'Raw' : '原值'} ${raw}` : ''}`
                  }}
                  formatter={(v) => [
                    `${(Number(v) * 100).toFixed(2)}%`,
                    locale === 'en' ? 'Drawdown' : '回撤',
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="dd"
                  name={locale === 'en' ? 'Drawdown' : '回撤'}
                  stroke="#9E1024"
                  strokeWidth={1.5}
                  fill="#C8102E"
                  fillOpacity={0.15}
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {/* (d) 逐笔明细 · 开仓笔 pnl/收益率 显「—」 */}
      <section>
        <h2 className="mb-3 font-serif text-lg font-bold">
          {locale === 'en' ? 'Trade log' : '逐笔明细'} ·{' '}
          {m
            ? locale === 'en'
              ? `${fmtInt(m.trade_count)} completed trades · `
              : `${fmtInt(m.trade_count)} 笔交易 · `
            : ''}
          {locale === 'en'
            ? `${trades.length} execution records`
            : `${trades.length} 条买卖记录`}
        </h2>
        {trades.length === 0 ? (
          <EmptyState
            title={locale === 'en' ? 'No executions' : '无成交'}
            hint={
              locale === 'en'
                ? 'The strategy produced no entries or exits in this period'
                : '该区间策略未触发任何买卖'
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-paper">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-paper bg-surface-card text-xs text-muted-foreground">
                  <th className="px-3 py-2 text-left font-medium">
                    {locale === 'en' ? 'Time' : '时间'}
                  </th>
                  <th className="px-3 py-2 text-left font-medium">
                    {locale === 'en' ? 'Side' : '方向'}
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    {locale === 'en' ? 'Price' : '价格'}
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    {locale === 'en' ? 'Quantity' : '数量'}
                  </th>
                  <th className="px-3 py-2 text-left font-medium">
                    {locale === 'en' ? 'Reason' : '原因'}
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    {locale === 'en' ? 'P&L' : '盈亏'}
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    {locale === 'en' ? 'Return' : '收益率'}
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    {locale === 'en' ? 'Holding days' : '持仓天数'}
                  </th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <TradeRow key={`${t.timestamp}-${i}`} trade={t} locale={locale} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-faint">
          {locale === 'en'
            ? 'Entry records do not realize per-trade P&L. P&L and return are calculated only when a position closes.'
            : '开仓笔(买入)不计单笔盈亏,盈亏 / 收益率显「—」;仅平仓笔(卖出)结算真实盈亏。'}
        </p>
      </section>

      {/* (e) run_card 方法学脚注 */}
      <MethodologyFootnote runCard={run.run_card_json} locale={locale} />
    </div>
  )
}

// ── 逐笔行(开仓 buy → pnl/收益率 显「—」)──────────────────────────────────────
function TradeRow({
  trade: t,
  locale,
}: {
  trade: Trade
  locale: 'en' | 'zh'
}) {
  const isOpen = t.side.toLowerCase() === 'buy' // 买入 = 开仓 · 不结算单笔盈亏
  const pnlTone = t.pnl > 0 ? 'text-up' : t.pnl < 0 ? 'text-down' : 'text-foreground'
  return (
    <tr className="border-b border-paper/60">
      <td className="px-3 py-2 text-xs text-muted-foreground">{t.timestamp}</td>
      <td className="px-3 py-2 text-xs">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] ${
            isOpen ? 'border border-midas-red text-midas-red' : 'bg-midas-red text-white'
          }`}
        >
          {isOpen
            ? locale === 'en' ? 'Buy · Open' : '买入 · 开'
            : locale === 'en' ? 'Sell · Close' : '卖出 · 平'}
        </span>
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums">{fmtNum(t.price)}</td>
      <td className="px-3 py-2 text-right font-mono tabular-nums">{t.qty}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {tradeReason(t.reason, locale)}
      </td>
      <td
        className={`px-3 py-2 text-right font-mono tabular-nums ${isOpen ? 'text-faint' : pnlTone}`}
      >
        {isOpen ? '—' : `${t.pnl >= 0 ? '+' : ''}${fmtNum(t.pnl)}`}
      </td>
      <td
        className={`px-3 py-2 text-right font-mono tabular-nums ${isOpen ? 'text-faint' : pnlTone}`}
      >
        {isOpen ? '—' : fmtPctNum(t.return_pct)}
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums text-muted-foreground">
        {t.holding_days.toFixed(1)}
      </td>
    </tr>
  )
}

// ── (e) 方法学脚注:run_card 渲染(防御式 · 形状未知)──────────────────────────
function MethodologyFootnote({
  runCard,
  locale,
}: {
  runCard: Record<string, unknown> | null
  locale: 'en' | 'zh'
}) {
  if (!runCard || Object.keys(runCard).length === 0) return null
  const dataSources = Array.isArray(runCard.data_sources)
    ? (runCard.data_sources as unknown[]).map((x) => String(x)).join(', ')
    : null
  return (
    <section className="rounded-lg border border-paper bg-surface-subtle p-4">
      <h2 className="mb-2 font-serif text-sm font-bold">
        {locale === 'en' ? 'Methodology · run_card' : '方法学 · run_card'}
      </h2>
      <p className="text-xs text-muted-foreground">
        {locale === 'en' ? 'Data source' : '数据源'}:
        {dataSources ?? (locale === 'en' ? 'Read-only ClickHouse (crypto perpetual)' : '只读 ClickHouse(crypto perp)')}
        {' · '}
        {locale === 'en'
          ? 'Strategy: deterministic dual-SMA crossover · No LLM'
          : '策略:SMA 双均线交叉(确定性 · 零 LLM)'}
      </p>
      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-muted-foreground/70">
          {locale === 'en'
            ? 'View the complete run_card (reproducibility / schema / warnings)'
            : '展开完整 run_card(可复现性 / schema / warnings)'}
        </summary>
        <pre className="mt-2 max-h-72 overflow-auto rounded bg-cream p-3 font-mono text-[11px] text-muted-foreground">
          {JSON.stringify(runCard, null, 2)}
        </pre>
      </details>
    </section>
  )
}

// ── 结论先行(从 metrics 动态生成)────────────────────────────────────────────
function conclusion(
  symbol: string,
  m: BacktestMetrics,
  locale: 'en' | 'zh',
): string {
  const beat = m.excess_return >= 0
  if (locale === 'en') {
    return (
      `The dual-SMA strategy returned ${fmtPct(m.total_return)} on ${symbol} perpetuals and ` +
      `${beat ? 'outperformed' : 'underperformed'} buy-and-hold by ${fmtPct(m.excess_return)}. ` +
      `Sharpe ${m.sharpe.toFixed(2)}, max drawdown ${fmtPct(m.max_drawdown)}, ` +
      `win rate ${fmtPct(m.win_rate)} across ${fmtInt(m.trade_count)} completed trades.`
    )
  }
  return (
    `结论:SMA 双均线策略在 ${symbol}(crypto perp)区间内总收益 ${fmtPct(m.total_return)},` +
    `${beat ? '跑赢' : '跑输'}买入持有基准(超额 ${fmtPct(m.excess_return)});` +
    `夏普 ${m.sharpe.toFixed(2)}、最大回撤 ${fmtPct(m.max_drawdown)}、` +
    `胜率 ${fmtPct(m.win_rate)}(共 ${fmtInt(m.trade_count)} 笔)。`
  )
}

function tradeReason(reason: string, locale: 'en' | 'zh'): string {
  if (locale === 'zh') return reason
  const translated = reason
    .replaceAll('SMA 快线上穿慢线', 'Fast SMA crossed above slow SMA')
    .replaceAll('SMA 快线下穿慢线', 'Fast SMA crossed below slow SMA')
    .replaceAll('快线上穿慢线', 'Fast SMA crossed above slow SMA')
    .replaceAll('快线下穿慢线', 'Fast SMA crossed below slow SMA')
    .replaceAll('金叉', 'bullish crossover')
    .replaceAll('死叉', 'bearish crossover')
    .replaceAll('买入', 'buy')
    .replaceAll('卖出', 'sell')
  return /[\u3400-\u9fff]/.test(translated) ? 'Dual-SMA crossover signal' : translated
}

function ErrorBox({ text }: { text: ReactNode }) {
  return (
    <div className="rounded-lg border border-midas-red/40 bg-midas-red/5 p-5 text-sm text-midas-red">
      {text}
    </div>
  )
}
