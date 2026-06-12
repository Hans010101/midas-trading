'use client'

/**
 * 现货订单流水(重组刀3 · 从 account/page 内联 OrdersTable 抽出,零逻辑改动)。
 */

import { useOrders } from '@/hooks/use-virtual'
import { currencyOf, formatMoney, MARKET_LABEL } from '@/lib/format-money'
import { cn } from '@/lib/utils'

export function SpotOrders() {
  const { data: orders = [] } = useOrders({ limit: 20 })

  if (orders.length === 0) return null

  return (
    <div className="mb-6">
      <h3 className="mb-2 font-serif text-base font-bold text-foreground">
        现货订单流水 · {orders.length} 笔
      </h3>
      {/* 移动刀B:横滚 wrapper(照 perp 表范式) */}
      <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
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
                    pnl !== null && pnl > 0 && 'text-up',
                    pnl !== null && pnl < 0 && 'text-down',
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
      </div>
    </div>
  )
}
