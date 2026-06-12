'use client'

/**
 * 现货历史持仓 · 复盘(重组刀3 · 从 account/page 内联 HistoricalTable 抽出,零逻辑改动)。
 */

import { usePositions } from '@/hooks/use-virtual'
import { currencyOf, formatMoney, MARKET_LABEL } from '@/lib/format-money'
import { cn } from '@/lib/utils'

export function SpotClosedPositions() {
  const { data: allPositions = [] } = usePositions({ includeClosed: true })
  const positions = allPositions.filter((p) => p.closed_at !== null)

  if (positions.length === 0) return null

  return (
    <div className="mb-6">
      <h3 className="mb-2 font-serif text-base font-bold text-foreground">
        现货历史持仓 · 复盘({positions.length})
      </h3>
      {/* 移动刀B:横滚 wrapper(照 perp 表范式) */}
      <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
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
                    realized > 0 && 'text-up',
                    realized < 0 && 'text-down',
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
      </div>
    </div>
  )
}
