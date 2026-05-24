'use client'

/**
 * 详情页「本币合约订单」· 单币视图(M2-C.1 验收补充)。
 *
 * 展示【当前 symbol】的已成交开/平流水(开多/开空/平多/平空 + 强平)·
 * 字段对齐 /account「合约订单流水」那张表。复用 /perp/orders(带 symbol 过滤)·
 * 不改后端、不碰账户页(账户页用 {limit:50} 无 symbol → queryKey 'all',互不干扰)。
 *
 * 🔴 红线:全程虚拟资金。这里是【已成交历史】,非挂单(限价/挂单是后续功能,本次不做)。
 * 仅登录用户显示;未登录返回 null(下单指导卡已处理登录引导)。
 */

import { useSession } from 'next-auth/react'

import { usePerpOrders } from '@/hooks/use-perp'
import type { PerpAction } from '@/lib/api/perp'
import { cn } from '@/lib/utils'

const ACTION_ZH: Record<PerpAction, string> = {
  open_long: '开多',
  open_short: '开空',
  close_long: '平多',
  close_short: '平空',
}

const num = (s: string | null | undefined): number => (s == null ? 0 : Number(s) || 0)
const fmtP = (s: string | null | undefined): string => {
  const n = num(s)
  return n >= 1 ? n.toLocaleString('en-US', { maximumFractionDigits: 2 }) : n.toFixed(4)
}
const fmtU = (s: string | null | undefined): string =>
  num(s).toLocaleString('en-US', { maximumFractionDigits: 2 })

export function CryptoPerpOrders({ futuresSymbol }: { futuresSymbol: string }) {
  const { status } = useSession()
  const { data: orders = [] } = usePerpOrders({ symbol: futuresSymbol, limit: 30 })

  if (status !== 'authenticated') return null

  return (
    <div className="rounded-lg border border-paper bg-cream/40 p-3">
      <div className="mb-2 font-serif text-sm font-bold text-foreground">
        本币合约订单 · {futuresSymbol}
      </div>
      {orders.length === 0 ? (
        <p className="py-4 text-center text-xs text-muted-foreground/60">暂无本币合约订单</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-[11px]">
            <thead>
              <tr className="border-b border-paper text-[10px] text-muted-foreground">
                <th className="py-1.5 text-left">时间</th>
                <th className="py-1.5 text-left">动作</th>
                <th className="py-1.5 text-right">数量</th>
                <th className="py-1.5 text-right">成交价</th>
                <th className="py-1.5 text-right">手续费</th>
                <th className="py-1.5 text-right">已实现</th>
                <th className="py-1.5 text-left">状态</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => {
                const pnl = o.realized_pnl != null ? num(o.realized_pnl) : null
                const ts = o.filled_at ?? o.placed_at
                return (
                  <tr
                    key={o.id ?? Math.random()}
                    className={cn('border-b border-paper/50', o.status === 'rejected' && 'opacity-60')}
                  >
                    <td className="py-1.5 text-[10px] text-muted-foreground">
                      {ts
                        ? new Date(ts).toLocaleString('zh-CN', {
                            month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                          })
                        : '—'}
                    </td>
                    <td className="py-1.5">
                      <span
                        className={cn(
                          'rounded px-1 py-0.5 text-[10px]',
                          o.action.startsWith('open')
                            ? 'bg-midas-red text-white'
                            : 'border border-midas-red text-midas-red',
                        )}
                      >
                        {ACTION_ZH[o.action]}
                      </span>
                      {o.is_liquidation && (
                        <span className="ml-1 rounded bg-bear/15 px-1 py-0.5 text-[9px] text-bear">强平</span>
                      )}
                    </td>
                    <td className="py-1.5 text-right font-mono">{num(o.quantity)}</td>
                    <td className="py-1.5 text-right font-mono">{o.price ? `$${fmtP(o.price)}` : '—'}</td>
                    <td className="py-1.5 text-right font-mono">{o.fee ? fmtU(o.fee) : '—'}</td>
                    <td
                      className={cn(
                        'py-1.5 text-right font-mono',
                        pnl != null && pnl > 0 && 'text-bull',
                        pnl != null && pnl < 0 && 'text-bear',
                      )}
                    >
                      {pnl != null ? `${pnl >= 0 ? '+' : ''}${fmtU(o.realized_pnl)}` : '—'}
                    </td>
                    <td className="py-1.5 text-[10px]">
                      {o.status === 'filled' ? (
                        <span className="text-muted-foreground">成交</span>
                      ) : (
                        <span className="text-midas-red" title={o.reject_reason ?? ''}>拒单</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[10px] text-muted-foreground/60">
        本币已成交开/平记录 · 全部币种见「我的账户」· 全程虚拟
      </p>
    </div>
  )
}
