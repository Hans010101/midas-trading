'use client'

/**
 * 合约历史持仓 · 复盘(重组刀3 · 从 perp-positions-section ②段拆出,零逻辑改动)。
 * 独立 query(includeClosed)· 未登录/无历史 → null。
 */

import { useMemo } from 'react'
import { useSession } from 'next-auth/react'

import { SideBadge, fmtP, fmtU, num } from '@/components/account/perp-shared'
import { usePerpPositions } from '@/hooks/use-perp'
import { cn } from '@/lib/utils'

export function PerpClosedPositions() {
  const { status } = useSession()
  const posQ = usePerpPositions({ includeClosed: true })

  const history = useMemo(
    () => (posQ.data ?? []).filter((p) => p.closed_at !== null),
    [posQ.data],
  )

  if (status !== 'authenticated' || history.length === 0) return null

  return (
    <details className="mb-6" open>
      <summary className="cursor-pointer font-serif text-base font-bold text-foreground">
        合约历史持仓 · 复盘({history.length})
      </summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-paper text-xs text-muted-foreground">
              <th className="py-2 text-left">标的</th>
              <th className="py-2 text-left">方向</th>
              <th className="py-2 text-right">入场价</th>
              <th className="py-2 text-right">已实现</th>
              <th className="py-2 text-left">平仓原因</th>
              <th className="py-2 text-left">开仓</th>
              <th className="py-2 text-left">平仓</th>
            </tr>
          </thead>
          <tbody>
            {history.map((p) => {
              const realized = num(p.realized_pnl)
              const liquidated = p.close_reason === 'liquidated'
              return (
                <tr key={p.id} className="border-b border-paper/60">
                  <td className="py-2 font-mono">{p.symbol}</td>
                  <td className="py-2"><SideBadge side={p.side} leverage={p.leverage} /></td>
                  <td className="py-2 text-right font-mono">${fmtP(p.entry_price)}</td>
                  <td className={cn('py-2 text-right font-mono', realized > 0 ? 'text-up' : realized < 0 ? 'text-down' : '')}>
                    {realized >= 0 ? '+' : ''}{fmtU(p.realized_pnl)}
                  </td>
                  <td className="py-2 text-xs">
                    <span className={cn('rounded px-1.5 py-0.5 text-[10px]', liquidated ? 'bg-down/15 text-down' : 'text-muted-foreground')}>
                      {liquidated ? '强平' : '手动平'}
                    </span>
                  </td>
                  <td className="py-2 text-xs text-muted-foreground">{new Date(p.opened_at).toLocaleString('zh-CN')}</td>
                  <td className="py-2 text-xs text-muted-foreground">
                    {p.closed_at ? new Date(p.closed_at).toLocaleString('zh-CN') : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </details>
  )
}
