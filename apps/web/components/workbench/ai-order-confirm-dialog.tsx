'use client'

/**
 * AI 一键模拟下单 · 二次确认模态 · 0036 批次甲。
 *
 * 复用手动下单确认模态(order-confirm-dialog)的【口径】(同壳 + VIRTUAL 徽章 + 二次确认步骤
 * + sonner toast),但路由到 ai-order 端点(source=ai_signal · 走同一虚拟撮合引擎 execute)。
 *
 * ★ 红线:① 只在用户点「确认」后才发请求(二次确认必经,绝不绕过);② 只调虚拟引擎,绝不接真实交易。
 * 仓位走用户下单预设(拍板③),此处不输入数量;成交数量在 toast 显示。
 */

import { useEffect } from 'react'
import { toast } from 'sonner'

import { VirtualBadge } from '@/components/ui/virtual-badge'
import { useKline } from '@/hooks/use-kline'
import { useAiOrder } from '@/hooks/use-virtual'
import { VirtualApiError } from '@/lib/api/virtual'
import { MARKET_LABEL, currencyOf, formatMoney } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

export type AiTradeDirection = 'buy' | 'sell' | 'open_long' | 'open_short'

const DIR_LABEL: Record<AiTradeDirection, string> = {
  buy: '买入', sell: '卖出', open_long: '开多', open_short: '开空',
}

interface Props {
  open: boolean
  onClose: () => void
  symbol: string
  market: Market
  direction: AiTradeDirection
  basis: string
  sizeNote: string
}

export function AiOrderConfirmDialog({
  open, onClose, symbol, market, direction, basis, sizeNote,
}: Props) {
  const currency = currencyOf(market)
  const { data: kline } = useKline({
    symbol, market, period: '1d', limit: 1, enabled: open,
  })
  const aiOrder = useAiOrder()

  // Esc 关闭(与手动模态一致)
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
  const dirLabel = DIR_LABEL[direction]
  const isOpenBuy = direction === 'buy' || direction === 'open_long'

  async function handleSubmit() {
    try {
      // ★ 二次确认后才发 · 走 ai-order(source=ai_signal · 同一虚拟撮合引擎)
      const res = await aiOrder.mutateAsync({ symbol, market, direction })
      if (res.filled) {
        toast.success(`${res.title} · ${res.detail}`, {
          className: 'midas-toast-success', duration: 4000,
        })
      } else {
        toast.error(`${res.title} · ${res.detail}`, { duration: 5000 })
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
          确认按 AI 建议模拟下单
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
                isOpenBuy
                  ? 'bg-midas-red text-white'
                  : 'border border-midas-red text-midas-red',
              )}
            >
              {dirLabel}
            </span>
          </Row>
          <Row label="仓位">
            <span className="text-foreground">{sizeNote}</span>
          </Row>

          <div className="my-2 border-t border-paper" />

          <Row label="AI 依据" muted>
            <span className="text-right text-foreground">{basis}</span>
          </Row>
          <Row label="市场价" muted>
            <span className="font-mono">
              {marketPrice
                ? formatMoney(marketPrice, currency, { decimals: market === 'crypto' ? 4 : 2 })
                : '—'}
            </span>
          </Row>
        </dl>

        <p className="mt-5 text-center text-[10px] text-muted-foreground/70">
          本次为模拟交易,不构成投资建议 · 成交数量按你的下单预设
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
            disabled={aiOrder.isPending}
            className={cn(
              'rounded-md px-4 py-2 text-sm font-medium text-white transition-colors',
              aiOrder.isPending
                ? 'bg-midas-red/30 cursor-not-allowed'
                : 'bg-midas-red hover:bg-midas-red-deep',
            )}
          >
            {aiOrder.isPending ? '提交中…' : `确认${dirLabel}`}
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
