'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import {
  actualLiqPrice,
  equityRatio,
  stepStatus,
  theoreticalLiqPrice,
  type StepStatus,
} from './liquidation-process.calc'
import { linearScale } from './use-svg-drag'

const ENTRY = 100
const MR = 0.005 // 维持保证金率 0.5%
const STEP = 2 // 每格下跌 2
const VB_W = 360
const VB_H = 220
const PLOT_TOP = 20
const PLOT_BOTTOM = 188
const X1 = 92
const X2 = 322
const AXIS_X = 76

const STATUS_STYLE: Record<StepStatus, { chip: string; text: string; label: string }> = {
  healthy: { chip: 'bg-success/10', text: 'text-success', label: '持仓健康' },
  warning: { chip: 'bg-warn/10', text: 'text-warn', label: '逼近强平' },
  liquidated: { chip: 'bg-midas-red/5', text: 'text-midas-red', label: '已强平' },
}

export function LiquidationProcessDemo() {
  const [leverage, setLeverage] = useState(10)
  const [price, setPrice] = useState(ENTRY)

  const theoLiq = theoreticalLiqPrice(leverage, ENTRY)
  const actLiq = actualLiqPrice(leverage, MR, ENTRY)
  const status = stepStatus(price, leverage, MR, ENTRY)
  const liquidated = status === 'liquidated'
  const ratio = Math.max(0, Math.min(1, equityRatio(price, leverage, ENTRY)))

  const P_MIN = Math.max(0, theoLiq - 3)
  const P_MAX = ENTRY + 3
  const priceToY = (p: number) => linearScale(p, P_MIN, P_MAX, PLOT_BOTTOM, PLOT_TOP)

  const stepDown = () => setPrice((p) => Math.max(actLiq, Number((p - STEP).toFixed(2))))
  const reset = () => setPrice(ENTRY)
  const changeLev = (v: number) => {
    setLeverage(v)
    setPrice(ENTRY) // 换杠杆即重置场景
  }

  const s = STATUS_STYLE[status]
  const yEntry = priceToY(ENTRY)
  const yTheo = priceToY(theoLiq)
  const yAct = priceToY(actLiq)
  const yPrice = priceToY(Math.max(P_MIN, price))

  return (
    <InteractiveCard
      title="爆仓是一步步逼近的"
      subtitle="多单、开仓价 100。点「再跌一格」让价格下跌,看保证金怎么被一格格吃掉、强平在哪一步触发。"
    >
      <label className="mb-3 flex items-center gap-3 text-sm">
        <span className="shrink-0 text-foreground/60">杠杆</span>
        <input type="range" min={3} max={50} step={1} value={leverage}
          onChange={(e) => changeLev(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="杠杆倍数" />
        <span className="w-12 shrink-0 text-right font-tabular font-semibold text-midas-red">{leverage}x</span>
      </label>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="h-auto w-full select-none" role="img" aria-label="爆仓全过程:价格逐步下跌逼近强平">
        <line x1={AXIS_X} y1={PLOT_TOP} x2={AXIS_X} y2={PLOT_BOTTOM} className="stroke-foreground/20" strokeWidth={1} />

        {/* 开仓价 */}
        <line x1={X1} y1={yEntry} x2={X2} y2={yEntry} className="stroke-foreground" strokeWidth={1.2} />
        <text x={X2} y={yEntry - 5} textAnchor="end" className="fill-foreground text-[11px]">开仓价 100</text>

        {/* 理论爆仓价(保证金归零) */}
        <line x1={X1} y1={yTheo} x2={X2} y2={yTheo} className="stroke-foreground/30" strokeWidth={1} strokeDasharray="4 3" />
        <text x={X2} y={yTheo + 13} textAnchor="end" className="fill-foreground/55 font-tabular text-[11px]">理论爆仓 {theoLiq.toFixed(1)}(保证金归零)</text>

        {/* 实际强平价(维持保证金,更早) */}
        <line x1={X1} y1={yAct} x2={X2} y2={yAct} className="stroke-midas-red" strokeWidth={1.8} />
        <text x={X1} y={yAct - 5} className="fill-midas-red font-tabular text-[11px] font-semibold">实际强平 {actLiq.toFixed(1)}(更早)</text>

        {/* 当前价标记 */}
        <line x1={X1} y1={yPrice} x2={X2} y2={yPrice} className={liquidated ? 'stroke-midas-red' : 'stroke-foreground/40'} strokeWidth={2} strokeDasharray="2 2" />
        <circle cx={X1} cy={yPrice} r={4} className={liquidated ? 'fill-midas-red' : 'fill-foreground'} />
        <text x={X1 + 8} y={yPrice - 5} className={'font-tabular text-[11px] font-semibold ' + (liquidated ? 'fill-midas-red' : 'fill-foreground')}>现价 {price.toFixed(1)}</text>
      </svg>

      {/* 保证金剩余条 */}
      <div className="mt-3">
        <div className="mb-1 flex justify-between text-[11px] text-foreground/60">
          <span>剩余保证金(权益)</span>
          <span className="font-tabular">{(ratio * 100).toFixed(0)}%</span>
        </div>
        <div className="h-3 w-full overflow-hidden rounded bg-surface-subtle">
          <div className={'h-full ' + (liquidated ? 'bg-midas-red' : status === 'warning' ? 'bg-warn' : 'bg-success')} style={{ width: `${ratio * 100}%` }} />
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button type="button" onClick={stepDown} disabled={liquidated}
          className={'rounded px-4 py-1.5 text-sm font-medium transition-colors ' + (liquidated ? 'cursor-not-allowed bg-surface-subtle text-foreground/40' : 'bg-midas-red text-white hover:bg-midas-red-deep')}>
          再跌一格 ↓
        </button>
        <button type="button" onClick={reset}
          className="rounded border border-paper px-4 py-1.5 text-sm text-foreground/70 transition-colors hover:bg-surface-subtle">
          重置
        </button>
        <span className={'ml-auto rounded px-2.5 py-1 text-xs font-medium ' + s.chip + ' ' + s.text}>{s.label}</span>
      </div>

      <p className="mt-3 text-sm text-foreground/85">
        {liquidated
          ? `已在 ${actLiq.toFixed(1)} 强平——注意:没等价格跌到理论的 ${theoLiq.toFixed(1)}(保证金归零),维持保证金让强平更早发生。`
          : `现价 ${price.toFixed(1)},剩余保证金 ${(ratio * 100).toFixed(0)}%。这一步你仍可主动止损——每一格都是机会。`}
      </p>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        爆仓是<strong className="text-foreground/80">一步步逼近、不是突然发生</strong>;维持保证金致实际强平比理论(保证金归零)<strong className="text-foreground/80">更早</strong>。杠杆越高,越少几格就触及强平。
      </p>
    </InteractiveCard>
  )
}
