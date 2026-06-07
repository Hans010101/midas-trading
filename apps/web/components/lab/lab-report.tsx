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
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { TopNav } from '@/components/layout/top-nav'
import { EmptyState, LoadingNote } from '@/components/ui/state'
import { useBacktestRun } from '@/hooks/use-backtest'
import type { BacktestMetrics, BacktestRunResponse, Trade } from '@/lib/api/backtest'

// ── 格式化 ──────────────────────────────────────────────────────────────────
function fmtPct(v: number): string {
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}
function fmtRatio(v: number): string {
  return v.toFixed(2)
}
function fmtInt(v: number): string {
  return String(Math.round(v))
}
function fmtNum(v: number): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

// ── 16 指标卡定义(tone:true → 按正负染 涨/跌 色)──────────────────────────────
type MetricKey = keyof BacktestMetrics
interface MetricDef {
  key: MetricKey
  label: string
  fmt: (v: number) => string
  tone?: boolean
}
const METRIC_DEFS: MetricDef[] = [
  { key: 'total_return', label: '总收益率', fmt: fmtPct, tone: true },
  { key: 'annual_return', label: '年化收益', fmt: fmtPct, tone: true },
  { key: 'max_drawdown', label: '最大回撤', fmt: fmtPct },
  { key: 'sharpe', label: '夏普比率', fmt: fmtRatio, tone: true },
  { key: 'sortino', label: '索提诺比率', fmt: fmtRatio, tone: true },
  { key: 'calmar', label: '卡玛比率', fmt: fmtRatio, tone: true },
  { key: 'win_rate', label: '胜率', fmt: fmtPct },
  { key: 'profit_loss_ratio', label: '盈亏比', fmt: fmtRatio },
  { key: 'profit_factor', label: '盈利因子', fmt: fmtRatio },
  { key: 'trade_count', label: '交易笔数', fmt: fmtInt },
  { key: 'max_consecutive_loss', label: '最大连亏', fmt: fmtInt },
  { key: 'avg_holding_days', label: '平均持仓(天)', fmt: (v) => v.toFixed(1) },
  { key: 'benchmark_return', label: '基准收益', fmt: fmtPct, tone: true },
  { key: 'excess_return', label: '超额收益', fmt: fmtPct, tone: true },
  { key: 'information_ratio', label: '信息比率', fmt: fmtRatio, tone: true },
  { key: 'final_value', label: '期末权益', fmt: fmtNum },
]

export function LabReport() {
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
          <EmptyState title="请先登录" hint="研究室回测需要登录后访问" />
        ) : id == null ? (
          <EmptyState title="缺少回测 id" hint="请从研究室列表进入" />
        ) : isError ? (
          <ErrorBox text={error?.message ?? '读取失败'} />
        ) : isPending || !run ? (
          <LoadingNote className="py-16" />
        ) : run.status === 'pending' ? (
          <LoadingNote className="py-16">回测进行中…(自动刷新)</LoadingNote>
        ) : run.status === 'error' ? (
          <ErrorBox text={`回测失败:${run.error ?? '未知错误'}`} />
        ) : (
          <ReportBody run={run} />
        )}
      </main>
    </div>
  )
}

// ── done 报告主体 ────────────────────────────────────────────────────────────
function ReportBody({ run }: { run: BacktestRunResponse }) {
  const m = run.metrics_json
  const equity = run.equity_json ?? []
  const trades = run.trades_json ?? []

  return (
    <div className="space-y-8">
      {/* (a) 结论先行 + 标的/区间 */}
      <section>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h1 className="font-serif text-2xl font-bold">回测报告</h1>
        </div>
        <p className="font-mono text-sm text-muted-foreground">
          {run.symbol} · crypto perp · {run.period} · {run.start_date} → {run.end_date}
        </p>
        {m && (
          <div className="mt-3 rounded-lg border border-paper bg-cream p-4 shadow-sm">
            <p className="text-sm leading-relaxed text-foreground">{conclusion(run.symbol, m)}</p>
          </div>
        )}
      </section>

      {/* (b) 16 指标卡 */}
      {m && (
        <section>
          <h2 className="mb-3 font-serif text-lg font-bold">关键指标</h2>
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
                  <div className="text-xs text-muted-foreground">{d.label}</div>
                  <div className={`mt-1 font-mono text-xl font-bold tabular-nums ${toneCls}`}>
                    {d.fmt(v)}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* (c) 双线收益曲线:策略 #C8102E 实线 + 基准 #94949C 虚线 */}
      <section>
        <h2 className="mb-3 font-serif text-lg font-bold">收益曲线</h2>
        <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
          {equity.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-sm text-faint">
              暂无曲线数据
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
                  name="策略"
                  stroke="#C8102E"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark_equity"
                  name="基准(买入持有)"
                  stroke="#94949C"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      {/* (d) 逐笔明细 · 开仓笔 pnl/收益率 显「—」 */}
      <section>
        <h2 className="mb-3 font-serif text-lg font-bold">逐笔明细 · {trades.length} 笔</h2>
        {trades.length === 0 ? (
          <EmptyState title="无成交" hint="该区间策略未触发任何买卖" />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-paper">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-paper bg-surface-card text-xs text-muted-foreground">
                  <th className="px-3 py-2 text-left font-medium">时间</th>
                  <th className="px-3 py-2 text-left font-medium">方向</th>
                  <th className="px-3 py-2 text-right font-medium">价格</th>
                  <th className="px-3 py-2 text-right font-medium">数量</th>
                  <th className="px-3 py-2 text-left font-medium">原因</th>
                  <th className="px-3 py-2 text-right font-medium">盈亏</th>
                  <th className="px-3 py-2 text-right font-medium">收益率</th>
                  <th className="px-3 py-2 text-right font-medium">持仓天数</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <TradeRow key={`${t.timestamp}-${i}`} trade={t} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-xs text-faint">
          开仓笔(买入)不计单笔盈亏,盈亏 / 收益率显「—」;仅平仓笔(卖出)结算真实盈亏。
        </p>
      </section>

      {/* (e) run_card 方法学脚注 */}
      <MethodologyFootnote runCard={run.run_card_json} />
    </div>
  )
}

// ── 逐笔行(开仓 buy → pnl/收益率 显「—」)──────────────────────────────────────
function TradeRow({ trade: t }: { trade: Trade }) {
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
          {isOpen ? '买入 · 开' : '卖出 · 平'}
        </span>
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums">{fmtNum(t.price)}</td>
      <td className="px-3 py-2 text-right font-mono tabular-nums">{t.qty}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{t.reason}</td>
      <td
        className={`px-3 py-2 text-right font-mono tabular-nums ${isOpen ? 'text-faint' : pnlTone}`}
      >
        {isOpen ? '—' : `${t.pnl >= 0 ? '+' : ''}${fmtNum(t.pnl)}`}
      </td>
      <td
        className={`px-3 py-2 text-right font-mono tabular-nums ${isOpen ? 'text-faint' : pnlTone}`}
      >
        {isOpen ? '—' : fmtPct(t.return_pct)}
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums text-muted-foreground">
        {t.holding_days.toFixed(1)}
      </td>
    </tr>
  )
}

// ── (e) 方法学脚注:run_card 渲染(防御式 · 形状未知)──────────────────────────
function MethodologyFootnote({ runCard }: { runCard: Record<string, unknown> | null }) {
  if (!runCard || Object.keys(runCard).length === 0) return null
  const dataSources = Array.isArray(runCard.data_sources)
    ? (runCard.data_sources as unknown[]).map((x) => String(x)).join(', ')
    : null
  return (
    <section className="rounded-lg border border-paper bg-surface-subtle p-4">
      <h2 className="mb-2 font-serif text-sm font-bold">方法学 · run_card</h2>
      <p className="text-xs text-muted-foreground">
        数据源:{dataSources ?? '只读 ClickHouse(crypto perp)'} · 策略:SMA 双均线交叉(确定性 · 零 LLM)
      </p>
      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-muted-foreground/70">
          展开完整 run_card(可复现性 / schema / warnings)
        </summary>
        <pre className="mt-2 max-h-72 overflow-auto rounded bg-cream p-3 font-mono text-[11px] text-muted-foreground">
          {JSON.stringify(runCard, null, 2)}
        </pre>
      </details>
    </section>
  )
}

// ── 结论先行(从 metrics 动态生成)────────────────────────────────────────────
function conclusion(symbol: string, m: BacktestMetrics): string {
  const beat = m.excess_return >= 0
  return (
    `结论:SMA 双均线策略在 ${symbol}(crypto perp)区间内总收益 ${fmtPct(m.total_return)},` +
    `${beat ? '跑赢' : '跑输'}买入持有基准(超额 ${fmtPct(m.excess_return)});` +
    `夏普 ${m.sharpe.toFixed(2)}、最大回撤 ${fmtPct(m.max_drawdown)}、` +
    `胜率 ${fmtPct(m.win_rate)}(共 ${fmtInt(m.trade_count)} 笔)。`
  )
}

function ErrorBox({ text }: { text: ReactNode }) {
  return (
    <div className="rounded-lg border border-midas-red/40 bg-midas-red/5 p-5 text-sm text-midas-red">
      {text}
    </div>
  )
}
