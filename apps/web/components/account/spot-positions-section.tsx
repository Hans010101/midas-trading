'use client'

/**
 * 现货当前持仓(重组刀3 · 从 account/page 内联 PositionsTable 抽出,表体零逻辑改动)。
 *
 * ★ 平仓操作链整体随段走:平仓按钮 → closeDialog 状态 → OrderConfirmDialog
 *   (usePlaceOrder · mutation 内部 invalidate)。原 page 层状态收进本组件,自包含。
 */

import { useState } from 'react'

import { OrderConfirmDialog } from '@/components/workbench/order-confirm-dialog'
import { usePortfolio, usePositions } from '@/hooks/use-virtual'
import type { AccountSummary } from '@/lib/api/virtual'
import { currencyOf, formatMoney, MARKET_LABEL } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

export function SpotPositionsSection() {
  const { data: activePositions = [] } = usePositions({ includeClosed: false })
  const { data: portfolio = [] } = usePortfolio()
  const [closeDialog, setCloseDialog] = useState<{
    open: boolean
    symbol: string
    market: Market
    quantity: string
  }>({ open: false, symbol: '', market: 'us', quantity: '0' })

  const summaryByMarket = new Map<string, AccountSummary>(
    portfolio.map((s) => [s.market, s]),
  )

  if (activePositions.length === 0) {
    return (
      <p className="mb-6 rounded-lg border border-paper bg-surface-card px-4 py-6 text-center text-sm text-muted-foreground/70">
        暂无现货持仓
      </p>
    )
  }

  return (
    <div className="mb-6">
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
          {activePositions.map((p) => {
            const summary = summaryByMarket.get(p.market)
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
                    unrealized !== null && unrealized > 0 && 'text-up',
                    unrealized !== null && unrealized < 0 && 'text-down',
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
                      setCloseDialog({
                        open: true, symbol: p.symbol,
                        market: p.market, quantity: p.quantity,
                      })
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
