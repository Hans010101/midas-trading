'use client'

/**
 * /account · 我的账户(段 1 补丁 B 重组)。
 *
 * Sections:
 *  1. 账户基本信息(邮箱)
 *  2. 虚拟资金设置(从原 /settings/wallet 迁来)
 *  3. KPI 卡 · 权益曲线 · 持仓 · 历史 · 订单(原 /portfolio 内容)
 *
 * 跟 /settings 区分:/settings 是「系统级配置」(推送 / 预警 / 偏好),
 * 这里是「账户级数据 + 资金管理」。
 */

import { useSession } from 'next-auth/react'
import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { PerpPositionsSection } from '@/components/account/perp-positions-section'
import { WalletSection } from '@/components/account/wallet-section'
import { TopNav } from '@/components/layout/top-nav'
import { VirtualBadge } from '@/components/ui/virtual-badge'
import { OrderConfirmDialog } from '@/components/workbench/order-confirm-dialog'
import {
  useAccounts,
  useEquityCurves,
  useOrders,
  usePortfolio,
  usePositions,
} from '@/hooks/use-virtual'
import type {
  AccountSummary,
  Currency,
  EquitySnapshot,
} from '@/lib/api/virtual'
import { currencyOf, formatMoney, MARKET_LABEL } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

export default function AccountPage() {
  const { data: session } = useSession()
  const { data: accounts = [], isLoading } = useAccounts()
  const { data: portfolio = [] } = usePortfolio()
  const { data: equityCurves } = useEquityCurves(30)
  const { data: activePositions = [] } = usePositions({ includeClosed: false })
  const { data: allPositions = [] } = usePositions({ includeClosed: true })
  const { data: orders = [] } = useOrders({ limit: 20 })

  const historicalPositions = allPositions.filter((p) => p.closed_at !== null)

  const [closeDialog, setCloseDialog] = useState<{
    open: boolean
    symbol: string
    market: Market
    quantity: string
  }>({ open: false, symbol: '', market: 'us', quantity: '0' })

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="mb-6 flex items-center gap-3">
          <h1 className="font-serif text-2xl font-bold text-foreground">
            我的账户
          </h1>
          <VirtualBadge size="sm" />
        </div>

        {/* Section 1: 账户基本信息 */}
        <section className="mb-10">
          <h2 className="mb-3 font-serif text-xl font-bold text-foreground">
            账户基本信息
          </h2>
          <div className="rounded-lg border border-paper bg-cream p-5 shadow-sm">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">邮箱</dt>
                <dd className="font-mono text-foreground">
                  {session?.user?.email ?? '—'}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">用户 ID</dt>
                <dd className="font-mono text-xs text-muted-foreground/70">
                  {session?.user?.id ?? '—'}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">账户类型</dt>
                <dd>
                  <span className="rounded bg-gold/[0.08] border border-gold px-2 py-0.5 font-mono text-[10px] text-gold">
                    VIRTUAL · 模拟
                  </span>
                </dd>
              </div>
            </dl>
          </div>
        </section>

        {/* Section 2: 虚拟资金设置(从旧 /settings/wallet 迁入)*/}
        <WalletSection />

        {/* Section 3: KPI + 曲线 + 持仓 + 历史 + 订单(仅有激活账户时显示)*/}
        {isLoading ? (
          <p className="py-12 text-center text-muted-foreground">载入中…</p>
        ) : accounts.length === 0 ? null : (
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

            {/* 活仓表 */}
            {activePositions.length > 0 && (
              <section className="mb-8">
                <h2 className="mb-3 font-serif text-lg font-bold text-foreground">
                  当前持仓 · {activePositions.length} 笔
                </h2>
                <PositionsTable
                  positions={activePositions}
                  portfolioMap={portfolioMap(portfolio)}
                  onClose={(p) =>
                    setCloseDialog({
                      open: true, symbol: p.symbol,
                      market: p.market, quantity: p.quantity,
                    })
                  }
                />
              </section>
            )}

            {/* 历史持仓 */}
            {historicalPositions.length > 0 && (
              <section className="mb-8">
                <h2 className="mb-3 font-serif text-lg font-bold text-foreground">
                  历史持仓 · 复盘
                </h2>
                <HistoricalTable positions={historicalPositions} />
              </section>
            )}

            {/* 订单流水 */}
            {orders.length > 0 && (
              <section className="mb-8">
                <h2 className="mb-3 font-serif text-lg font-bold text-foreground">
                  最近订单 · {orders.length} 笔
                </h2>
                <OrdersTable orders={orders} />
              </section>
            )}
          </>
        )}

        {/* 加密合约(永续)持仓 / 订单中心 · M2-C.1 · 独立 Section,自身按 crypto 激活态门控 */}
        <PerpPositionsSection />

        <p className="mt-12 text-center text-xs text-muted-foreground/70">
          模拟交易,不构成投资建议
        </p>
      </main>

      <OrderConfirmDialog
        open={closeDialog.open}
        onClose={() => setCloseDialog({ ...closeDialog, open: false })}
        symbol={closeDialog.symbol}
        market={closeDialog.market}
        side="sell"
        closeAllQuantity={closeDialog.quantity}
      />
    </div>
  )
}

function portfolioMap(
  portfolio: AccountSummary[],
): Map<string, AccountSummary> {
  return new Map(portfolio.map((s) => [s.market, s]))
}

// ===== KPI 卡 =====

function KPICard({ summary }: { summary: AccountSummary }) {
  const currency = summary.currency
  const realized = Number(summary.realized_pnl)
  const equity = Number(summary.total_equity)
  const initial = Number(summary.initial_capital)
  const totalPct = initial > 0 ? ((equity - initial) / initial) * 100 : 0
  const realizedPctClass =
    realized > 0 ? 'text-bull' : realized < 0 ? 'text-bear' : 'text-muted-foreground'

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

// ===== 活仓表 =====

interface PositionsTableProps {
  positions: {
    id: number
    symbol: string
    market: Market
    quantity: string
    avg_entry_price: string
  }[]
  portfolioMap: Map<string, AccountSummary>
  onClose: (p: { symbol: string; market: Market; quantity: string }) => void
}

function PositionsTable({ positions, portfolioMap, onClose }: PositionsTableProps) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-paper text-xs text-muted-foreground">
          <th className="py-2 text-left">标的</th>
          <th className="py-2 text-left">市场</th>
          <th className="py-2 text-right">数量</th>
          <th className="py-2 text-right">均价</th>
          <th className="py-2 text-right">现价</th>
          <th className="py-2 text-right">浮盈亏</th>
          <th className="py-2 text-right">操作</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => {
          const summary = portfolioMap.get(p.market)
          const view = summary?.positions.find(
            (pv) => pv.symbol === p.symbol && pv.market === p.market,
          )
          const currency = currencyOf(p.market)
          const unrealized = view?.unrealized_pnl ? Number(view.unrealized_pnl) : null
          return (
            <tr key={p.id} className="border-b border-paper/60">
              <td className="py-2 font-mono">{p.symbol}</td>
              <td className="py-2 text-xs">{MARKET_LABEL[p.market]}</td>
              <td className="py-2 text-right font-mono">{Number(p.quantity).toLocaleString()}</td>
              <td className="py-2 text-right font-mono">
                {formatMoney(p.avg_entry_price, currency, { decimals: 4 })}
              </td>
              <td className="py-2 text-right font-mono">
                {view?.current_price
                  ? formatMoney(view.current_price, currency, { decimals: 4 })
                  : '—'}
              </td>
              <td
                className={cn(
                  'py-2 text-right font-mono',
                  unrealized !== null && unrealized > 0 && 'text-bull',
                  unrealized !== null && unrealized < 0 && 'text-bear',
                )}
              >
                {unrealized !== null
                  ? formatMoney(unrealized, currency, { sign: true })
                  : '—'}
              </td>
              <td className="py-2 text-right">
                <button
                  type="button"
                  onClick={() =>
                    onClose({ symbol: p.symbol, market: p.market, quantity: p.quantity })
                  }
                  className="rounded border border-midas-red px-2 py-1 text-xs text-midas-red hover:bg-midas-red-glow"
                >
                  平仓
                </button>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ===== 历史持仓 =====

function HistoricalTable({
  positions,
}: {
  positions: { id: number; symbol: string; market: Market; avg_entry_price: string; realized_pnl: string | null; opened_at: string; closed_at: string | null }[]
}) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-paper text-xs text-muted-foreground">
          <th className="py-2 text-left">标的</th>
          <th className="py-2 text-left">市场</th>
          <th className="py-2 text-right">均价</th>
          <th className="py-2 text-right">已实现</th>
          <th className="py-2 text-left">开仓</th>
          <th className="py-2 text-left">平仓</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => {
          const realized = p.realized_pnl ? Number(p.realized_pnl) : 0
          const currency = currencyOf(p.market)
          return (
            <tr key={p.id} className="border-b border-paper/60">
              <td className="py-2 font-mono">{p.symbol}</td>
              <td className="py-2 text-xs">{MARKET_LABEL[p.market]}</td>
              <td className="py-2 text-right font-mono">
                {formatMoney(p.avg_entry_price, currency, { decimals: 4 })}
              </td>
              <td
                className={cn(
                  'py-2 text-right font-mono',
                  realized > 0 && 'text-bull',
                  realized < 0 && 'text-bear',
                )}
              >
                {p.realized_pnl
                  ? formatMoney(p.realized_pnl, currency, { sign: true })
                  : '—'}
              </td>
              <td className="py-2 text-xs text-muted-foreground">
                {new Date(p.opened_at).toLocaleString('zh-CN')}
              </td>
              <td className="py-2 text-xs text-muted-foreground">
                {p.closed_at ? new Date(p.closed_at).toLocaleString('zh-CN') : '—'}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ===== 订单流水 =====

function OrdersTable({
  orders,
}: {
  orders: {
    id: number | null; symbol: string; market: Market
    side: 'buy' | 'sell'; quantity: string; price: string | null
    notional: string | null; commission: string | null
    realized_pnl: string | null; status: 'filled' | 'rejected'
    reject_reason: string | null; placed_at: string | null
  }[]
}) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-paper text-xs text-muted-foreground">
          <th className="py-2 text-left">时间</th>
          <th className="py-2 text-left">方向</th>
          <th className="py-2 text-left">标的</th>
          <th className="py-2 text-right">数量</th>
          <th className="py-2 text-right">成交价</th>
          <th className="py-2 text-right">手续费</th>
          <th className="py-2 text-right">P/L</th>
          <th className="py-2 text-left">状态</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((o) => {
          const currency = currencyOf(o.market)
          const pnl = o.realized_pnl ? Number(o.realized_pnl) : null
          return (
            <tr
              key={o.id ?? Math.random()}
              className={cn(
                'border-b border-paper/60',
                o.status === 'rejected' && 'opacity-60',
              )}
            >
              <td className="py-2 text-xs text-muted-foreground">
                {o.placed_at
                  ? new Date(o.placed_at).toLocaleString('zh-CN', {
                      month: '2-digit', day: '2-digit',
                      hour: '2-digit', minute: '2-digit',
                    })
                  : '—'}
              </td>
              <td className="py-2 text-xs">
                <span
                  className={cn(
                    'rounded px-1.5 py-0.5 text-[10px]',
                    o.side === 'buy'
                      ? 'bg-midas-red text-white'
                      : 'border border-midas-red text-midas-red',
                  )}
                >
                  {o.side === 'buy' ? '买入' : '卖出'}
                </span>
              </td>
              <td className="py-2 font-mono text-xs">
                {o.symbol}
                <span className="ml-1 text-muted-foreground">· {MARKET_LABEL[o.market]}</span>
              </td>
              <td className="py-2 text-right font-mono text-xs">
                {Number(o.quantity).toLocaleString()}
              </td>
              <td className="py-2 text-right font-mono text-xs">
                {o.price ? formatMoney(o.price, currency, { decimals: 4 }) : '—'}
              </td>
              <td className="py-2 text-right font-mono text-xs">
                {o.commission ? formatMoney(o.commission, currency, { decimals: 4 }) : '—'}
              </td>
              <td
                className={cn(
                  'py-2 text-right font-mono text-xs',
                  pnl !== null && pnl > 0 && 'text-bull',
                  pnl !== null && pnl < 0 && 'text-bear',
                )}
              >
                {pnl !== null
                  ? formatMoney(pnl, currency, { sign: true })
                  : '—'}
              </td>
              <td className="py-2 text-xs">
                {o.status === 'filled' ? (
                  <span className="text-muted-foreground">成交</span>
                ) : (
                  <span className="text-midas-red" title={o.reject_reason ?? ''}>
                    拒单
                  </span>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
