'use client'

/**
 * 共享条件单弹层(ADR 0041 刀3)· 限价挂单 + 持仓挂止损/止盈 共用一个组件。
 *
 * ★ F1 教训:spot 下单 UI 多组件多页面 —— SL/TP 入口必须用【同一个 dialog】插多处
 *   (spot-order-panel / workbench current-position-card / perp ActivePositionCard),
 *   杜绝「同功能不同页面不同组件」漏页面翻车。
 *
 * mode='limit':spot 限价挂单(side 由入口传入;crypto 不出 LIMIT —— 后端 400)。
 * mode='sltp' :持仓挂止损/止盈(side 自动推平仓方向 LONG→SELL / SHORT→BUY;
 *               数量留空 = 触发时平全仓)。
 *
 * 价源:与后端触发器同源(spot 1d 末根 close;crypto perp 1d 末根 close)· 仅提示用。
 * 🔴 红线:全程虚拟资金 · 前端只挂单,成交由后端 60s 扫描走唯一虚拟撮合入口。
 */

import { useState } from 'react'
import { toast } from 'sonner'

import { useKline } from '@/hooks/use-kline'
import { usePlaceConditionalOrder } from '@/hooks/use-conditional-orders'
import { ConditionalApiError } from '@/lib/api/conditional-order'
import type { OrderSide, PositionSide } from '@/lib/api/virtual'
import {
  type ConditionalKind,
  deviationPct,
  kindLabel,
  wouldTriggerNow,
} from '@/lib/conditional'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

interface ConditionalOrderDialogProps {
  open: boolean
  onClose: () => void
  symbol: string
  name?: string | null
  market: Market
  /** limit=限价挂单(spot 面板入口)· sltp=持仓挂止损/止盈(持仓入口) */
  mode: 'limit' | 'sltp'
  /** limit 模式必传:买卖方向 */
  side?: OrderSide
  /** sltp 模式必传:持仓方向(平仓方向自动推导) */
  positionSide?: PositionSide
  /** sltp 模式:当前持仓量(展示「全仓 ≈ N」) */
  heldQuantity?: string | null
  /** limit 模式:预填数量(spot 面板带入) */
  defaultQuantity?: string
  /** kline 取价 symbol(crypto 传 ccxt 风格 BTC/USDT;省略 = 用 symbol) */
  klineSymbol?: string
}

export function ConditionalOrderDialog({
  open, onClose, symbol, name, market, mode,
  side, positionSide, heldQuantity, defaultQuantity, klineSymbol,
}: ConditionalOrderDialogProps) {
  const [kind, setKind] = useState<'stop_loss' | 'take_profit'>('stop_loss')
  const [triggerPrice, setTriggerPrice] = useState('')
  const [quantity, setQuantity] = useState(defaultQuantity ?? '')
  const place = usePlaceConditionalOrder()

  // 现价(提示用)· 与后端触发器价源同源:spot/crypto 都取 1d 末根 close
  const { data: kline } = useKline({
    symbol: klineSymbol ?? symbol,
    market,
    period: '1d',
    limit: 1,
    ...(market === 'crypto' ? { instrument: 'perp' as const } : {}),
  })
  const currentPrice = kline?.items?.at(-1)?.close ?? null

  if (!open) return null

  const effKind: ConditionalKind = mode === 'limit' ? 'limit' : kind
  const effPositionSide: PositionSide = positionSide ?? 'long'
  // SL/TP 平仓方向自动推导(后端端点同口径校验:LONG→SELL / SHORT→BUY)
  const effSide: OrderSide = mode === 'limit' ? (side ?? 'buy') : effPositionSide === 'long' ? 'sell' : 'buy'
  const actionLabel = kindLabel(effKind, effSide)

  const triggerNum = Number(triggerPrice) || 0
  const qtyNum = Number(quantity) || 0
  const quantityValid = mode === 'limit' ? qtyNum > 0 : quantity.trim() === '' || qtyNum > 0
  const canSubmit = !place.isPending && triggerNum > 0 && quantityValid

  const deviation = triggerNum > 0 ? deviationPct(triggerNum, currentPrice) : null
  const instantTrigger =
    triggerNum > 0 && currentPrice != null
    && wouldTriggerNow(effKind, effSide, effPositionSide, triggerNum, currentPrice)

  async function handleSubmit() {
    try {
      await place.mutateAsync({
        symbol,
        market,
        order_kind: effKind,
        side: effSide,
        ...(effPositionSide === 'short' ? { position_side: 'short' as const } : {}),
        trigger_price: triggerPrice.trim(),
        // SL/TP 留空 = 平全仓(不传 quantity);LIMIT 必填
        ...(quantity.trim() !== '' ? { quantity: quantity.trim() } : {}),
      })
      toast.success(`已挂${actionLabel} ${symbol} @ ${triggerPrice}(虚拟)· 到价即触发`, {
        className: 'midas-toast-success', duration: 4000,
      })
      onClose()
    } catch (e) {
      toast.error(e instanceof ConditionalApiError ? e.detail : '挂单失败')
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
      {/* 虚拟标识:对齐现有面板口径(帝王金框 + 文案)· 不新造徽章 */}
      <div className="w-full max-w-md rounded-lg border border-gold/60 bg-cream p-6 shadow-xl">
        <h3 className="mb-1 text-center font-serif text-xl font-bold text-foreground">
          {mode === 'limit' ? '挂限价单(虚拟)' : '设止损 / 止盈(虚拟)'}
        </h3>
        <p className="mb-4 text-center font-mono text-xs text-muted-foreground">
          {symbol}
          {name && <span className="ml-1">· {name}</span>}
        </p>

        {/* sltp:止损 / 止盈 二选一 */}
        {mode === 'sltp' && (
          <div className="mb-3 flex overflow-hidden rounded-md border border-paper text-sm">
            {(['stop_loss', 'take_profit'] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={cn(
                  'flex-1 px-3 py-1.5 transition-colors',
                  kind === k
                    ? 'bg-midas-red text-white'
                    : 'text-muted-foreground hover:bg-midas-red-glow/50',
                )}
              >
                {k === 'stop_loss' ? '止损' : '止盈'}
              </button>
            ))}
          </div>
        )}

        {/* 操作摘要 */}
        <div className="mb-3 flex items-center justify-between text-xs text-muted-foreground">
          <span>触发后操作</span>
          <span className="rounded bg-midas-red px-2 py-0.5 text-xs font-medium text-white">
            {actionLabel}
            {mode === 'sltp' && (effPositionSide === 'short' ? '(买入平空)' : '(卖出平仓)')}
          </span>
        </div>

        {/* 触发价 */}
        <label className="mb-1 block text-xs text-muted-foreground">
          触发价
          {currentPrice != null && (
            <span className="ml-2 font-mono text-muted-foreground/70">现价 {currentPrice}</span>
          )}
        </label>
        <input
          type="number"
          value={triggerPrice}
          onChange={(e) => setTriggerPrice(e.target.value)}
          min={0}
          placeholder="必填 · 到价即触发"
          className="mb-3 h-9 w-full rounded border border-paper bg-background px-3 text-right font-mono text-sm"
        />

        {/* 数量 */}
        <label className="mb-1 block text-xs text-muted-foreground">
          数量
          {mode === 'sltp' && heldQuantity && (
            <span className="ml-2 font-mono text-muted-foreground/70">
              留空 = 平全仓(当前 {Number(heldQuantity)})
            </span>
          )}
        </label>
        <input
          type="number"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          min={0}
          placeholder={mode === 'sltp' ? '留空 = 触发时平全仓' : '必填'}
          className="mb-3 h-9 w-full rounded border border-paper bg-background px-3 text-right font-mono text-sm"
        />

        {/* 提示区 */}
        {instantTrigger && (
          <p className="mb-2 rounded-md border border-gold/60 bg-gold/10 px-3 py-2 text-xs text-gold">
            当前价已满足触发条件 · 挂单后约 1 分钟内即会按市价成交(到价即触发,语义如此)
          </p>
        )}
        {!instantTrigger && deviation != null && deviation > 50 && (
          <p className="mb-2 rounded-md border border-gold/60 bg-gold/10 px-3 py-2 text-xs text-gold">
            触发价偏离现价 {deviation.toFixed(1)}%,请确认
          </p>
        )}

        <p className="mb-4 text-[11px] leading-relaxed text-muted-foreground/70">
          全程虚拟资金 · 系统每分钟扫描,到价即触发 · 以触发时市价成交(含滑点/费率)·
          余额/持仓在触发时校验,不足则挂单失效。
        </p>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground hover:bg-cream"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
            className={cn(
              'rounded-md px-4 py-2 text-sm font-medium text-white transition-colors',
              canSubmit ? 'bg-midas-red hover:bg-midas-red-deep' : 'cursor-not-allowed bg-midas-red/30',
            )}
          >
            {place.isPending ? '提交中…' : `挂${actionLabel}`}
          </button>
        </div>
      </div>
    </div>
  )
}
