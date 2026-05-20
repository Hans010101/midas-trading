'use client'

/**
 * 下单确认模态 · 0008 v2 § 8.3 必经。
 *
 * 7 字段 + VIRTUAL 徽章 + 实时算成本 + 中国红主按钮 + Esc 取消。
 * 所有下单入口(顶部按钮 / 右键 / Cmd+B/S / 一键平仓)共用此模态。
 *
 * 提交后弹 sonner toast(R10)· 帝王金成功 / 中国红失败 · 永不绿色。
 */

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { VirtualBadge } from '@/components/ui/virtual-badge'
import { useAccount, usePlaceOrder } from '@/hooks/use-virtual'
import { useKline } from '@/hooks/use-kline'
import { VirtualApiError } from '@/lib/api/virtual'
import { estimateOrder } from '@/lib/fees'
import { MARKET_LABEL, currencyOf, formatMoney } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

interface Props {
  open: boolean
  onClose: () => void
  symbol: string
  market: Market
  side: 'buy' | 'sell'
  /** 一键平仓 · 直接传持仓量,模态不让改 */
  closeAllQuantity?: string
}

export function OrderConfirmDialog({
  open, onClose, symbol, market, side, closeAllQuantity,
}: Props) {
  const currency = currencyOf(market)
  const { data: account } = useAccount(market)
  // 拿最新 K 算市场价(跟 watchlist quote 同源)
  const { data: kline } = useKline({
    symbol, market, period: '1d', limit: 1, enabled: open,
  })
  const placeOrder = usePlaceOrder()

  const defaultQty = closeAllQuantity ?? defaultQuantityFor(market)
  const [quantity, setQuantity] = useState(defaultQty)

  // 模态打开时重置默认数量
  useEffect(() => {
    if (open) setQuantity(closeAllQuantity ?? defaultQuantityFor(market))
  }, [open, market, closeAllQuantity])

  // Esc 关闭
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const marketPrice = kline?.items?.[kline.items.length - 1]?.close ?? null
  const qtyNum = Number(quantity) || 0
  const estimate = marketPrice && qtyNum > 0
    ? estimateOrder(market, side, marketPrice, qtyNum)
    : null

  const available = account ? Number(account.cash_balance) : 0
  const hasEnoughBalance = side === 'sell'
    || (estimate !== null && estimate.totalCost <= available)
  const sideLabel = side === 'buy' ? '买入' : '卖出'
  const canSubmit =
    !placeOrder.isPending
    && qtyNum > 0
    && estimate !== null
    && hasEnoughBalance

  async function handleSubmit() {
    try {
      const order = await placeOrder.mutateAsync({
        symbol, market, side, quantity: quantity.trim(),
      })
      if (order.status === 'filled') {
        toast.success(
          `${sideLabel} ${quantity} ${symbol} 已成交 · ${formatMoney(order.notional ?? '0', currency)}`,
          { className: 'midas-toast-success', duration: 4000 },
        )
      } else {
        toast.error(
          `下单被拒 · ${order.reject_reason ?? '未知原因'}`,
          { duration: 5000 },
        )
      }
      onClose()
    } catch (e) {
      const msg = e instanceof VirtualApiError ? e.detail : '下单失败'
      toast.error(msg)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-md rounded-lg border border-midas-red bg-cream p-6 shadow-xl">
        <div className="mb-3 flex justify-center">
          <VirtualBadge size="sm" />
        </div>
        <h3 className="mb-5 text-center font-serif text-xl font-bold text-foreground">
          确认下单
        </h3>

        <dl className="space-y-3 text-sm">
          <Row label="标的">
            <span className="font-mono">{symbol}</span>
            <span className="ml-2 text-xs text-muted-foreground">
              · {MARKET_LABEL[market]}
            </span>
          </Row>
          <Row label="方向">
            <span
              className={cn(
                'rounded px-2 py-0.5 text-xs font-medium',
                side === 'buy'
                  ? 'bg-midas-red text-white'
                  : 'border border-midas-red text-midas-red',
              )}
            >
              {sideLabel}
            </span>
          </Row>
          <Row label="数量">
            {closeAllQuantity ? (
              <span className="font-mono">{quantity}(全部平仓)</span>
            ) : (
              <input
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                min={0}
                step={market === 'crypto' ? 0.0001 : 1}
                className="h-8 w-32 rounded border border-paper bg-background px-2 text-right font-mono text-sm"
              />
            )}
          </Row>

          <div className="my-2 border-t border-paper" />

          <Row label="市场价" muted>
            <span className="font-mono">
              {marketPrice ? formatMoney(marketPrice, currency, { decimals: market === 'crypto' ? 4 : 2 }) : '—'}
            </span>
          </Row>
          <Row label="预估成交价" muted>
            <span className="font-mono">
              {estimate ? formatMoney(estimate.fillPrice, currency, { decimals: market === 'crypto' ? 4 : 4 }) : '—'}
              <span className="ml-1 text-xs text-muted-foreground/70">
                (含滑点)
              </span>
            </span>
          </Row>
          <Row label="预估手续费" muted>
            <span className="font-mono">
              {estimate ? formatMoney(estimate.commission, currency, { decimals: 4 }) : '—'}
            </span>
          </Row>
          <Row label="滑点成本" muted>
            <span className="font-mono">
              {estimate ? formatMoney(estimate.slippageCost, currency, { decimals: 4 }) : '—'}
            </span>
          </Row>

          <div className="my-2 border-t border-paper" />

          <Row label={side === 'buy' ? '预估总成本' : '预估收到'}>
            <span className="font-mono text-base font-bold text-midas-red">
              {estimate ? formatMoney(estimate.totalCost, currency) : '—'}
            </span>
          </Row>
          <Row label="可用余额" muted>
            <span className="font-mono">
              {formatMoney(available, currency)}
            </span>
          </Row>
        </dl>

        {side === 'buy' && estimate && !hasEnoughBalance && (
          <p className="mt-3 rounded-md bg-midas-red-glow px-3 py-2 text-xs text-midas-red">
            余额不足 · 差 {formatMoney(estimate.totalCost - available, currency)}
          </p>
        )}

        <p className="mt-5 text-center text-[10px] text-muted-foreground/70">
          本次为模拟交易,不构成投资建议
        </p>

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground hover:bg-cream"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={cn(
              'rounded-md px-4 py-2 text-sm font-medium text-white transition-colors',
              canSubmit
                ? 'bg-midas-red hover:bg-midas-red-deep'
                : 'bg-midas-red/30 cursor-not-allowed',
            )}
          >
            {placeOrder.isPending
              ? '提交中…'
              : `确认${sideLabel}`}
          </button>
        </div>
      </div>
    </div>
  )
}

function Row({
  label, children, muted,
}: {
  label: string; children: React.ReactNode; muted?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt
        className={cn(
          'text-xs',
          muted ? 'text-muted-foreground/70' : 'text-muted-foreground',
        )}
      >
        {label}
      </dt>
      <dd className="text-right text-foreground">{children}</dd>
    </div>
  )
}

function defaultQuantityFor(market: Market): string {
  if (market === 'cn') return '100'
  if (market === 'us') return '1'
  return '0.01'
}
