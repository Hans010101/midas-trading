'use client'

/**
 * 条件单列表(ADR 0041 刀3)· 详情页(按 symbol 过滤)+ account 页(全量)两用。
 *
 * 照 crypto-perp-orders 表格范式 + alert-rules 撤单范式(✕ 不弹确认 ——
 * 条件单无资金冻结,撤错可重挂)。30s 轮询(hook 内),active→triggered 自动可见。
 * 状态:active=金 · triggered=朱红(链 /account 看成交单)· cancelled/expired=灰
 * (expired 的 note 用 title tooltip 露出拒因)。
 */

import Link from 'next/link'
import { useSession } from 'next-auth/react'

import { useCancelConditionalOrder, useConditionalOrders } from '@/hooks/use-conditional-orders'
import { STATUS_ZH, kindLabel } from '@/lib/conditional'
import { MARKET_LABEL } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

interface ConditionalOrdersListProps {
  /** 传入 = 详情页单币视图(隐藏标的/市场列);省略 = account 全量视图 */
  symbol?: string
  market?: Market
}

export function ConditionalOrdersList({ symbol, market }: ConditionalOrdersListProps) {
  const { status } = useSession()
  const { data: all = [] } = useConditionalOrders()
  const cancel = useCancelConditionalOrder()

  if (status !== 'authenticated') return null

  const rows = all.filter(
    (o) => (symbol == null || o.symbol === symbol) && (market == null || o.market === market),
  )
  const singleSymbol = symbol != null
  // 详情页:没挂过单就不占版面;account 全量:常驻显示(空态文案)
  if (singleSymbol && rows.length === 0) return null

  return (
    <div className="rounded-lg border border-paper bg-surface-card p-3">
      <div className="mb-2 font-serif text-sm font-bold text-foreground">
        {singleSymbol ? `本币条件单 · ${symbol}` : '条件单'}
      </div>
      {rows.length === 0 ? (
        <p className="py-4 text-center text-xs text-muted-foreground/60">
          暂无条件单 · 可在详情页下单区挂限价单,或在持仓上设止损/止盈
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className={cn('w-full text-[11px]', singleSymbol ? 'min-w-[420px]' : 'min-w-[560px]')}>
            <thead>
              <tr className="border-b border-paper text-[10px] text-muted-foreground">
                <th className="py-1.5 text-left">时间</th>
                {!singleSymbol && <th className="py-1.5 text-left">标的</th>}
                <th className="py-1.5 text-left">类型</th>
                <th className="py-1.5 text-right">触发价</th>
                <th className="py-1.5 text-right">数量</th>
                <th className="py-1.5 text-left">状态</th>
                <th className="py-1.5 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id} className={cn('border-b border-paper/50', (o.status === 'cancelled' || o.status === 'expired') && 'opacity-60')}>
                  <td className="py-1.5 text-[10px] text-muted-foreground">
                    {new Date(o.created_at).toLocaleString('zh-CN', {
                      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                    })}
                  </td>
                  {!singleSymbol && (
                    <td className="py-1.5">
                      <span className="font-mono">{o.symbol}</span>
                      <span className="ml-1 text-[9px] text-muted-foreground/70">
                        {MARKET_LABEL[o.market as Market] ?? o.market}
                      </span>
                    </td>
                  )}
                  <td className="py-1.5">
                    <span
                      className={cn(
                        'rounded px-1 py-0.5 text-[10px]',
                        o.order_kind === 'limit'
                          ? 'bg-midas-red text-white'
                          : 'border border-midas-red text-midas-red',
                      )}
                    >
                      {kindLabel(o.order_kind, o.side)}
                    </span>
                  </td>
                  <td className="py-1.5 text-right font-mono">{Number(o.trigger_price)}</td>
                  <td className="py-1.5 text-right font-mono">
                    {o.quantity != null ? Number(o.quantity) : '全仓'}
                  </td>
                  <td className="py-1.5 text-[10px]">
                    <StatusCell
                      status={o.status}
                      note={o.note}
                      triggeredOrderId={o.triggered_order_id}
                    />
                  </td>
                  <td className="py-1.5 text-right">
                    {o.status === 'active' && (
                      <button
                        type="button"
                        onClick={() => cancel.mutate(o.id)}
                        disabled={cancel.isPending}
                        aria-label="撤销条件单"
                        title="撤销(无资金冻结 · 撤错可重挂)"
                        className="text-muted-foreground/60 transition-colors hover:text-midas-red disabled:opacity-40"
                      >
                        ✕
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[10px] text-muted-foreground/60">
        全程虚拟资金 · 每分钟扫描 · 到价以市价成交{singleSymbol && ' · 全部市场见「我的账户」'}
      </p>
    </div>
  )
}

function StatusCell({
  status, note, triggeredOrderId,
}: {
  status: 'active' | 'triggered' | 'cancelled' | 'expired'
  note: string | null
  triggeredOrderId: number | null
}) {
  if (status === 'active') {
    return <span className="rounded border border-gold bg-gold/10 px-1 py-0.5 text-gold">{STATUS_ZH.active}</span>
  }
  if (status === 'triggered') {
    return (
      <Link
        href="/account"
        title="去「我的账户」查看成交单"
        className="rounded bg-midas-red px-1 py-0.5 text-white hover:bg-midas-red-deep"
      >
        {STATUS_ZH.triggered}
        {triggeredOrderId != null && <span className="ml-0.5 font-mono">#{triggeredOrderId}</span>}
      </Link>
    )
  }
  return (
    <span className="text-muted-foreground" title={note ?? undefined}>
      {STATUS_ZH[status]}
      {status === 'expired' && note && <span className="ml-0.5 cursor-help">ⓘ</span>}
    </span>
  )
}
