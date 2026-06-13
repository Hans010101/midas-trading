'use client'

/**
 * 共享条件单弹层(ADR 0041 刀3 + 二期刀3)· 限价挂单 + 持仓挂止损/止盈 共用一个组件。
 *
 * ★ F1 教训:spot 下单 UI 多组件多页面 —— SL/TP 入口必须用【同一个 dialog】插多处
 *   (spot-order-panel / workbench current-position-card / perp ActivePositionCard),
 *   杜绝「同功能不同页面不同组件」漏页面翻车。
 *
 * mode='limit'     :spot 限价挂单(side 由入口传入)。
 * mode='sltp'      :持仓挂止损/止盈(side 自动推平仓方向 LONG→SELL / SHORT→BUY;
 *                    数量留空 = 触发时平全仓)。
 * mode='perp-limit':perp 限价开仓(二期刀3)· 方向开多/开空 + 杠杆 + 保证金 + 仓位模式;
 *                    quantity 不填(margin×leverage 定仓,与后端 route_open_perp 口径一致)。
 *
 * 价源:与后端触发器同源(spot 1d 末根 close;crypto perp 标记价优先)· 仅提示用。
 * 🔴 红线:全程虚拟资金 · 前端只挂单,成交由后端 60s 扫描走唯一虚拟撮合入口。
 */

import { useState } from 'react'
import { toast } from 'sonner'

import { useFuturesInfo } from '@/hooks/use-crypto'
import { useKline } from '@/hooks/use-kline'
import { usePlaceConditionalOrder } from '@/hooks/use-conditional-orders'
import { ConditionalApiError, type MarginMode } from '@/lib/api/conditional-order'
import type { OrderSide, PositionSide } from '@/lib/api/virtual'
import {
  type ConditionalKind,
  PERP_LIMIT_MAX_LEVERAGE,
  PERP_LIMIT_MIN_LEVERAGE,
  deviationPct,
  kindLabel,
  presetDirection,
  presetTriggerPrice,
  validatePerpLimit,
  wouldTriggerNow,
} from '@/lib/conditional'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

type DialogMode = 'limit' | 'sltp' | 'perp-limit'

interface ConditionalOrderDialogProps {
  open: boolean
  onClose: () => void
  symbol: string
  name?: string | null
  market: Market
  /** limit=spot 限价 · sltp=持仓止损止盈 · perp-limit=perp 限价开仓(刀3) */
  mode: DialogMode
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
  const isPerpLimit = mode === 'perp-limit'
  const [kind, setKind] = useState<'stop_loss' | 'take_profit'>('stop_loss')
  const [triggerPrice, setTriggerPrice] = useState('')
  const [quantity, setQuantity] = useState(defaultQuantity ?? '')
  // perp 限价开仓表单(仅 perp-limit 模式用)
  const [direction, setDirection] = useState<PositionSide>('long')
  const [leverage, setLeverage] = useState(10)
  const [margin, setMargin] = useState('1000')
  const [marginMode, setMarginMode] = useState<MarginMode>('isolated')
  const place = usePlaceConditionalOrder()

  // 现价(提示 + 快捷档位基准):
  //   crypto(perp)→ 标记价优先(premium_index 1min 新鲜 · 与触发器 route_close/open_perp 同源)
  //   股票(cn/us/hk)→ 1d 末根 close 不变(各市场有 kline 采集任务,新鲜)
  const { data: kline } = useKline({
    symbol: klineSymbol ?? symbol,
    market,
    period: '1d',
    limit: 1,
    ...(market === 'crypto' ? { instrument: 'perp' as const } : {}),
  })
  // crypto 入口的 symbol prop 即 Binance 风格(BTCUSDT)· 非 crypto 不请求
  const { data: futuresInfo } = useFuturesInfo(symbol, market === 'crypto')
  const klineClose = kline?.items?.at(-1)?.close ?? null
  const currentPrice = market === 'crypto' ? (futuresInfo?.mark_price ?? klineClose) : klineClose

  if (!open) return null

  // perp 限价:方向决定 side(开多 BUY / 开空 SELL)+ position_side;后端 _OPENING_SIDE 同口径
  const effKind: ConditionalKind = mode === 'sltp' ? kind : 'limit'
  const effPositionSide: PositionSide = isPerpLimit ? direction : (positionSide ?? 'long')
  const effSide: OrderSide = isPerpLimit
    ? (direction === 'long' ? 'buy' : 'sell')
    : mode === 'limit'
      ? (side ?? 'buy')
      : effPositionSide === 'long' ? 'sell' : 'buy'
  const actionLabel = isPerpLimit
    ? (direction === 'long' ? '限价开多' : '限价开空')
    : kindLabel(effKind, effSide)

  const triggerNum = Number(triggerPrice) || 0
  const qtyNum = Number(quantity) || 0
  const marginNum = Number(margin) || 0
  const perpLimitError = isPerpLimit
    ? validatePerpLimit({ triggerPrice: triggerNum, leverage, margin: marginNum, marginMode })
    : null
  const quantityValid = mode === 'limit' ? qtyNum > 0 : quantity.trim() === '' || qtyNum > 0
  const canSubmit = isPerpLimit
    ? !place.isPending && perpLimitError == null
    : !place.isPending && triggerNum > 0 && quantityValid

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
        ...(isPerpLimit
          // perp 限价开仓:杠杆/保证金/模式必填 · quantity 不传(margin×leverage 定仓)
          ? { leverage, margin: margin.trim(), margin_mode: marginMode }
          // SL/TP 留空 = 平全仓(不传 quantity);spot LIMIT 必填
          : quantity.trim() !== '' ? { quantity: quantity.trim() } : {}),
      })
      toast.success(`已挂${actionLabel} ${symbol} @ ${triggerPrice} · 到价即触发`, {
        className: 'midas-toast-success', duration: 4000,
      })
      onClose()
    } catch (e) {
      toast.error(e instanceof ConditionalApiError ? e.detail : '挂单失败')
    }
  }

  const title = isPerpLimit
    ? '挂限价单(永续)'
    : mode === 'limit' ? '挂限价单' : '设止损 / 止盈'

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
        <h3 className="mb-1 text-center font-serif text-xl font-bold text-foreground">{title}</h3>
        <p className="mb-4 text-center font-mono text-xs text-muted-foreground">
          {symbol}
          {name && <span className="ml-1">· {name}</span>}
        </p>

        {/* perp 限价:开多 / 开空 方向 */}
        {isPerpLimit && (
          <div className="mb-3 grid grid-cols-2 gap-2">
            {(['long', 'short'] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDirection(d)}
                aria-pressed={direction === d}
                className={cn(
                  'rounded-md py-2 text-sm font-medium transition-colors',
                  direction === d
                    ? 'bg-midas-red text-white'
                    : 'border border-midas-red/50 text-midas-red hover:bg-midas-red-glow/40',
                )}
              >
                {d === 'long' ? '开多' : '开空'}
              </button>
            ))}
          </div>
        )}

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
          className="mb-1.5 h-9 w-full rounded border border-paper bg-background px-3 text-right font-mono text-sm"
        />

        {/* 快捷档位:按【不立即触发】方向取价填入(presetDirection 与触发矩阵互证)·
            只填值不提交 · 用户可再微调 · 不预填(初始仍空) */}
        {currentPrice != null && currentPrice > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-1.5">
            {[0.02, 0.05, 0.1].map((pct) => {
              const dir = presetDirection(effKind, effSide, effPositionSide)
              const price = presetTriggerPrice(effKind, effSide, effPositionSide, currentPrice, pct)
              return (
                <button
                  key={pct}
                  type="button"
                  onClick={() => setTriggerPrice(price)}
                  title={`现价×${(1 + dir * pct).toFixed(2)} = ${price}(现价${dir === -1 ? '下' : '上'}方 ${pct * 100}%)`}
                  className="rounded border border-paper px-2 py-0.5 font-mono text-[11px] text-muted-foreground transition-colors hover:border-gold/60 hover:text-gold"
                >
                  {dir === -1 ? '−' : '+'}
                  {pct * 100}%
                </button>
              )
            })}
            <span className="text-[10px] text-muted-foreground/60">点档位按方向取价 · 可微调</span>
          </div>
        )}

        {/* perp 限价:保证金模式 + 杠杆 + 保证金(开仓参数 · margin×leverage 定仓) */}
        {isPerpLimit ? (
          <>
            <div className="mb-3">
              <div className="mb-1 text-xs text-muted-foreground">保证金模式</div>
              <div className="grid grid-cols-2 gap-2">
                {(['isolated', 'cross'] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMarginMode(m)}
                    aria-pressed={marginMode === m}
                    className={cn(
                      'rounded-md py-1.5 text-xs transition-colors',
                      marginMode === m
                        ? 'border border-gold bg-gold/[0.08] font-medium text-gold'
                        : 'border border-paper text-muted-foreground/70 hover:border-gold/40',
                    )}
                  >
                    {m === 'isolated' ? '逐仓 isolated' : '全仓 cross'}
                  </button>
                ))}
              </div>
            </div>
            <div className="mb-3">
              <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                <span>杠杆</span>
                <span className="font-mono font-bold text-foreground">{leverage}x</span>
              </div>
              <input
                type="range"
                min={PERP_LIMIT_MIN_LEVERAGE}
                max={PERP_LIMIT_MAX_LEVERAGE}
                step={1}
                value={leverage}
                onChange={(e) => setLeverage(Number(e.target.value))}
                className="w-full accent-midas-red"
              />
            </div>
            <label className="mb-1 block text-xs text-muted-foreground">保证金(USDT)</label>
            <input
              type="number"
              value={margin}
              min={0}
              step={50}
              onChange={(e) => setMargin(e.target.value)}
              placeholder="必填 · 触发时按 margin×杠杆 开仓"
              className="mb-3 h-9 w-full rounded border border-paper bg-background px-3 text-right font-mono text-sm"
            />
          </>
        ) : (
          <>
            {/* 数量(limit / sltp) */}
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
          </>
        )}

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
          系统每分钟扫描,到价即触发 · 以触发时市价成交(含滑点/费率)·
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
            title={perpLimitError ?? undefined}
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
