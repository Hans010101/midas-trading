'use client'

/**
 * 合约订单流水 + 资金费记录(重组刀3 · 从 perp-positions-section ③④段拆出,零逻辑改动)。
 * 两段同为流水性质 · 各自独立 query · 未登录/空 → null。
 */

import { useSession } from 'next-auth/react'

import { ACTION_ZH, fmtP, fmtU, num } from '@/components/account/perp-shared'
import { usePerpFunding, usePerpOrders } from '@/hooks/use-perp'
import type { PerpFunding } from '@/lib/api/perp'
import { cn } from '@/lib/utils'

export function PerpOrders() {
  const { status } = useSession()
  const ordersQ = usePerpOrders({ limit: 50 })
  const fundingQ = usePerpFunding({ limit: 50 })

  const orders = ordersQ.data ?? []
  const funding = fundingQ.data ?? []

  if (status !== 'authenticated' || (orders.length === 0 && funding.length === 0)) return null

  return (
    <div>
      {/* ③ 合约订单流水 */}
      {orders.length > 0 && (
        <>
          <h3 className="mb-2 font-serif text-base font-bold text-foreground">
            合约订单流水 · {orders.length} 笔
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="border-b border-paper text-xs text-muted-foreground">
                  <th className="py-2 text-left">时间</th>
                  <th className="py-2 text-left">动作</th>
                  <th className="py-2 text-left">标的</th>
                  <th className="py-2 text-right">数量</th>
                  <th className="py-2 text-right">成交价</th>
                  <th className="py-2 text-right">手续费</th>
                  <th className="py-2 text-right">已实现</th>
                  <th className="py-2 text-left">状态</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => {
                  const pnl = o.realized_pnl != null ? num(o.realized_pnl) : null
                  return (
                    <tr key={o.id ?? Math.random()} className={cn('border-b border-paper/60', o.status === 'rejected' && 'opacity-60')}>
                      <td className="py-2 text-xs text-muted-foreground">
                        {o.placed_at || o.filled_at
                          ? new Date(o.filled_at ?? o.placed_at!).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
                          : '—'}
                      </td>
                      <td className="py-2 text-xs">
                        <span className={cn('rounded px-1.5 py-0.5 text-[10px]', o.action.startsWith('open') ? 'bg-midas-red text-white' : 'border border-midas-red text-midas-red')}>
                          {ACTION_ZH[o.action]}
                        </span>
                        {o.is_liquidation && <span className="ml-1 rounded bg-down/15 px-1 py-0.5 text-[9px] text-down">强平</span>}
                      </td>
                      <td className="py-2 font-mono text-xs">{o.symbol}{o.leverage ? <span className="ml-1 text-muted-foreground">{o.leverage}x</span> : null}</td>
                      <td className="py-2 text-right font-mono text-xs">{num(o.quantity)}</td>
                      <td className="py-2 text-right font-mono text-xs">{o.price ? `$${fmtP(o.price)}` : '—'}</td>
                      <td className="py-2 text-right font-mono text-xs">{o.fee ? fmtU(o.fee) : '—'}</td>
                      <td className={cn('py-2 text-right font-mono text-xs', pnl != null && pnl > 0 ? 'text-up' : pnl != null && pnl < 0 ? 'text-down' : '')}>
                        {pnl != null ? `${pnl >= 0 ? '+' : ''}${fmtU(o.realized_pnl)}` : '—'}
                      </td>
                      <td className="py-2 text-xs">
                        {o.status === 'filled'
                          ? <span className="text-muted-foreground">成交</span>
                          : <span className="text-midas-red" title={o.reject_reason ?? ''}>拒单</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ④ 资金费记录(M2-C.2.2)· 每整点按币周期结算 · 只读复盘 */}
      {funding.length > 0 && (
        <>
          <h3 className="mb-2 mt-6 font-serif text-base font-bold text-foreground">
            资金费记录 · {funding.length} 笔
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-paper text-xs text-muted-foreground">
                  <th className="py-2 text-left">结算时刻</th>
                  <th className="py-2 text-left">标的</th>
                  <th className="py-2 text-left">方向</th>
                  <th className="py-2 text-right">资金费率</th>
                  <th className="py-2 text-right">标记价</th>
                  <th className="py-2 text-right">数量</th>
                  <th className="py-2 text-right">金额</th>
                </tr>
              </thead>
              <tbody>
                {funding.map((f: PerpFunding) => {
                  const pay = num(f.payment)
                  const rate = num(f.funding_rate)
                  return (
                    <tr key={f.id} className="border-b border-paper/60">
                      <td className="py-2 text-xs text-muted-foreground">
                        {new Date(f.funding_ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td className="py-2 font-mono text-xs">{f.symbol}</td>
                      <td className="py-2">
                        <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold text-white', f.side === 'long' ? 'bg-up' : 'bg-down')}>
                          {f.side === 'long' ? '多' : '空'}
                        </span>
                      </td>
                      <td className={cn('py-2 text-right font-mono text-xs', rate >= 0 ? 'text-up' : 'text-down')}>
                        {rate >= 0 ? '+' : ''}{(rate * 100).toFixed(4)}%
                      </td>
                      <td className="py-2 text-right font-mono text-xs">${fmtP(f.mark_price)}</td>
                      <td className="py-2 text-right font-mono text-xs">{num(f.quantity)}</td>
                      <td className={cn('py-2 text-right font-mono text-xs', pay > 0 ? 'text-down' : pay < 0 ? 'text-up' : 'text-muted-foreground/60')}>
                        {pay === 0 ? '0' : pay > 0 ? `付 ${fmtU(f.payment)}` : `收 ${fmtU(String(-pay))}`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground/60">
            资金费率为正:多头付、空头收 · 每币按各自结算周期(8h/4h…)在整点结算 · 只扣虚拟现金
          </p>
        </>
      )}
    </div>
  )
}
