'use client'

/**
 * 右栏 · 当前标的持仓摘要 · 0008 v2 § 8.5。
 *
 * 只在当前 market + symbol 在用户活仓里时显示。
 * 帝王金 border + 显眼 + 一键平仓(走 OrderConfirmDialog · closeAllQuantity)。
 */

import { useState } from 'react'

import { ConditionalOrderDialog } from '@/components/trading/conditional-order-dialog'
import { OrderConfirmDialog } from '@/components/workbench/order-confirm-dialog'
import { usePortfolio } from '@/hooks/use-virtual'
import { currencyOf, formatMoney, formatPct } from '@/lib/format-money'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'

export function CurrentPositionCard() {
  const symbol = useWorkbenchStore((s) => s.symbol)
  const market = useWorkbenchStore((s) => s.market)
  const { data: portfolio } = usePortfolio()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [sltpOpen, setSltpOpen] = useState(false)

  // 找当前 market 子账户 + 当前 symbol 活仓
  const summary = portfolio?.find((s) => s.market === market)
  const position = summary?.positions.find(
    (p) => p.symbol === symbol && p.market === market,
  )

  if (!position) return null

  const currency = currencyOf(market)
  const unrealized = position.unrealized_pnl ? Number(position.unrealized_pnl) : null
  const value = position.value ? Number(position.value) : null
  const avgEntry = Number(position.avg_entry_price)
  const pct = unrealized !== null && value !== null && avgEntry > 0
    ? (Number(position.unrealized_pnl) / (Number(position.quantity) * avgEntry)) * 100
    : null

  return (
    <section className="m-3 rounded-md border-2 border-gold bg-cream p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-xs font-medium text-foreground">
            {position.symbol}
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground">持仓中</span>
      </div>

      <dl className="space-y-1 text-xs">
        <div className="flex justify-between">
          <dt className="text-muted-foreground">数量</dt>
          <dd className="font-mono text-foreground">
            {Number(position.quantity).toLocaleString()}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">均价</dt>
          <dd className="font-mono text-foreground">
            {formatMoney(position.avg_entry_price, currency, { decimals: 4 })}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">现价</dt>
          <dd className="font-mono text-foreground">
            {position.current_price
              ? formatMoney(position.current_price, currency, { decimals: 4 })
              : '—'}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">浮盈亏</dt>
          <dd
            className={cn(
              'font-mono',
              unrealized !== null && unrealized > 0 && 'text-up',
              unrealized !== null && unrealized < 0 && 'text-down',
              unrealized === null && 'text-muted-foreground/60',
            )}
          >
            {unrealized !== null
              ? formatMoney(unrealized, currency, { sign: true })
              : '—'}
            {pct !== null && (
              <span className="ml-1 text-[10px]">({formatPct(pct)})</span>
            )}
          </dd>
        </div>
      </dl>

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          className="flex-1 rounded-md bg-midas-red px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-midas-red-deep"
        >
          一键平仓
        </button>
        {/* 持仓挂 SL/TP(共享 ConditionalOrderDialog)· crypto tab 不出:workbench crypto 是
            spot 持仓,而条件单 crypto 语义=perp(后端按 perp 活仓校验/平仓),错位 → 留二期 */}
        {market !== 'crypto' && (
          <button
            type="button"
            onClick={() => setSltpOpen(true)}
            className="rounded-md border border-gold/60 px-3 py-1.5 text-xs text-gold transition-colors hover:bg-gold/10"
          >
            止损/止盈
          </button>
        )}
      </div>

      <OrderConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        symbol={position.symbol}
        market={position.market}
        side="sell"
        closeAllQuantity={position.quantity}
      />
      {sltpOpen && (
        <ConditionalOrderDialog
          open
          onClose={() => setSltpOpen(false)}
          symbol={position.symbol}
          market={position.market}
          mode="sltp"
          positionSide={position.position_side}
          heldQuantity={position.quantity}
        />
      )}
    </section>
  )
}
