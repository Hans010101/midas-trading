'use client'

/**
 * 账户实时全貌:KPI 卡 + 权益曲线(重组刀3 · 从 account/page 内联抽出,零逻辑改动)。
 * 持仓/订单各表已搬模块②(/account/positions)· 本组件只留资产视角。
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useAccounts, useEquityCurves, usePortfolio } from '@/hooks/use-virtual'
import type { AccountSummary, Currency, EquitySnapshot } from '@/lib/api/virtual'
import { formatMoney, MARKET_LABEL } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

export function AccountOverview() {
  const { data: accounts = [], isLoading } = useAccounts()
  const { data: portfolio = [] } = usePortfolio()
  const { data: equityCurves } = useEquityCurves(30)

  if (isLoading) {
    return <p className="py-12 text-center text-muted-foreground">载入中…</p>
  }
  if (accounts.length === 0) return null

  return (
    <>
      <div className="mb-3 flex items-center gap-2">
        <h2 className="font-serif text-xl font-bold text-foreground">
          账户实时全貌
        </h2>
      </div>
      {/* KPI 卡:N 张并列 */}
      <div
        className={cn(
          'mb-8 grid gap-4',
          accounts.length === 1 && 'grid-cols-1',
          accounts.length === 2 && 'grid-cols-1 md:grid-cols-2',
          accounts.length === 3 && 'grid-cols-1 md:grid-cols-3',
        )}
      >
        {portfolio.map((s) => (
          <KPICard key={s.market} summary={s} />
        ))}
      </div>

      {/* 曲线:N 张 */}
      <h2 className="mb-3 font-serif text-lg font-bold text-foreground">
        权益曲线 · 过去 30 天
      </h2>
      <div
        className={cn(
          'mb-8 grid gap-4',
          accounts.length === 1 && 'grid-cols-1',
          accounts.length === 2 && 'grid-cols-1 md:grid-cols-2',
          accounts.length === 3 && 'grid-cols-1 md:grid-cols-3',
        )}
      >
        {portfolio.map((s) => (
          <EquityCurveCard
            key={s.market}
            market={s.market}
            currency={s.currency}
            points={equityCurves?.curves?.[s.market] ?? []}
          />
        ))}
      </div>
    </>
  )
}

// ===== KPI 卡 =====

function KPICard({ summary }: { summary: AccountSummary }) {
  const currency = summary.currency
  const realized = Number(summary.realized_pnl)
  const equity = Number(summary.total_equity)
  const initial = Number(summary.initial_capital)
  const totalPct = initial > 0 ? ((equity - initial) / initial) * 100 : 0
  const realizedPctClass =
    realized > 0 ? 'text-up' : realized < 0 ? 'text-down' : 'text-muted-foreground'

  return (
    <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="font-serif text-base font-bold text-foreground">
          {MARKET_LABEL[summary.market]}
        </h3>
        <span className="font-mono text-[10px] text-muted-foreground">
          {currency}
        </span>
      </div>
      <div className="mb-3">
        <p className="font-mono text-2xl font-bold text-foreground">
          {formatMoney(summary.total_equity, currency)}
        </p>
        <p className={cn('mt-0.5 font-mono text-xs', realizedPctClass)}>
          {totalPct >= 0 ? '+' : ''}
          {totalPct.toFixed(2)}% (初始 {formatMoney(summary.initial_capital, currency)})
        </p>
      </div>
      <div className="space-y-1 text-xs text-muted-foreground">
        <div className="flex justify-between">
          <span>现金</span>
          <span className="font-mono">{formatMoney(summary.cash_balance, currency)}</span>
        </div>
        <div className="flex justify-between">
          <span>持仓市值</span>
          <span className="font-mono">{formatMoney(summary.positions_value, currency)}</span>
        </div>
        <div className="flex justify-between">
          <span>累计已实现</span>
          <span className={cn('font-mono', realizedPctClass)}>
            {formatMoney(summary.realized_pnl, currency, { sign: true })}
          </span>
        </div>
      </div>
    </div>
  )
}

// ===== 曲线 =====

function EquityCurveCard({
  market, currency, points,
}: {
  market: Market; currency: Currency; points: EquitySnapshot[]
}) {
  const data = points.map((p) => ({
    t: new Date(p.snapshot_at).toLocaleDateString('zh-CN', {
      month: '2-digit', day: '2-digit',
    }),
    equity: Number(p.equity),
  }))
  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="font-serif text-sm font-bold text-foreground">
          {MARKET_LABEL[market]} 权益
        </h3>
        <span className="font-mono text-[10px] text-muted-foreground">{currency}</span>
      </div>
      {data.length === 0 ? (
        <div className="flex h-32 items-center justify-center text-xs text-muted-foreground/60">
          暂无快照数据
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F7F6F1" />
            <XAxis dataKey="t" fontSize={10} tick={{ fill: '#94949C' }} />
            <YAxis
              fontSize={10}
              tick={{ fill: '#94949C' }}
              domain={['auto', 'auto']}
              tickFormatter={(v) => Number(v).toLocaleString()}
            />
            <Tooltip
              contentStyle={{
                background: '#FCFCF9',
                border: '1px solid #C8102E',
                fontSize: 12,
              }}
              labelStyle={{ color: '#1A1A1A' }}
              formatter={(v) => formatMoney(Number(v ?? 0), currency)}
            />
            <Line
              type="monotone"
              dataKey="equity"
              stroke="#C8102E"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
