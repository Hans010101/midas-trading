'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { linearScale } from './use-svg-drag'
import { ENTRY_PRICE, bufferPct, liquidationPrice, type Side } from './liquidation.calc'

const VB_W = 360
const VB_H = 300
const PLOT_TOP = 28
const PLOT_BOTTOM = 252
const AXIS_X = 132
const LINE_X1 = 96
const LINE_X2 = 322
const P_MIN = 0
const P_MAX = 200

const priceToY = (p: number) => linearScale(p, P_MIN, P_MAX, PLOT_BOTTOM, PLOT_TOP)
const clampPrice = (p: number) => Math.max(P_MIN, Math.min(P_MAX, p))

export function LiquidationDemo() {
  const [leverage, setLeverage] = useState(10)
  const [side, setSide] = useState<Side>('long')

  const isLong = side === 'long'
  const liq = liquidationPrice(side, leverage)
  const buffer = bufferPct(side, leverage)
  // 实际强平更早:开仓价与理论爆仓价之间、靠开仓价一侧(示意取 70% 处)
  const realLiq = ENTRY_PRICE + (liq - ENTRY_PRICE) * 0.7

  const yEntry = priceToY(ENTRY_PRICE)
  const yLiq = priceToY(clampPrice(liq))
  const yReal = priceToY(clampPrice(realLiq))

  return (
    <InteractiveCard
      title="爆仓价随杠杆移动"
      subtitle="开仓价固定为 100。拖动杠杆滑块、切换多空,看爆仓价线怎么移动。"
    >
      <div className="mb-4 flex flex-col gap-3">
        <div className="inline-flex self-start overflow-hidden rounded border border-paper">
          {(['long', 'short'] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              aria-pressed={side === s}
              className={
                'px-4 py-1.5 text-sm font-medium transition-colors ' +
                (side === s
                  ? 'bg-midas-red text-white'
                  : 'bg-surface-card text-foreground/60 hover:text-foreground')
              }
            >
              {s === 'long' ? '做多' : '做空'}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-3 text-sm">
          <span className="shrink-0 text-foreground/60">杠杆</span>
          <input
            type="range"
            min={1}
            max={100}
            step={1}
            value={leverage}
            onChange={(e) => setLeverage(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer accent-midas-red"
            aria-label="杠杆倍数"
          />
          <span className="w-12 shrink-0 text-right font-tabular font-semibold text-midas-red">
            {leverage}x
          </span>
        </label>
      </div>

      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        className="h-auto w-full select-none"
        role="img"
        aria-label={`杠杆 ${leverage} 倍${isLong ? '多单' : '空单'}的爆仓价示意`}
      >
        <line x1={AXIS_X} y1={PLOT_TOP} x2={AXIS_X} y2={PLOT_BOTTOM} className="stroke-foreground/20" strokeWidth={1} />
        {[0, 50, 100, 150, 200].map((p) => (
          <g key={p}>
            <line x1={AXIS_X - 4} y1={priceToY(p)} x2={AXIS_X} y2={priceToY(p)} className="stroke-foreground/20" strokeWidth={1} />
            <text x={AXIS_X - 8} y={priceToY(p) + 3} textAnchor="end" className="fill-foreground/55 font-tabular text-[10px]">
              {p}
            </text>
          </g>
        ))}

        {/* 容错空间(开仓价 ↔ 爆仓价) */}
        <rect
          x={LINE_X1}
          y={Math.min(yEntry, yLiq)}
          width={LINE_X2 - LINE_X1}
          height={Math.abs(yLiq - yEntry)}
          className="fill-midas-red/5"
        />

        {/* 开仓价线 */}
        <line x1={LINE_X1} y1={yEntry} x2={LINE_X2} y2={yEntry} className="stroke-foreground" strokeWidth={1.5} />
        <text x={LINE_X2} y={yEntry - 6} textAnchor="end" className="fill-foreground text-[11px] font-medium">
          开仓价 100
        </text>

        {/* 实际强平线(更早) */}
        <line x1={LINE_X1} y1={yReal} x2={LINE_X2} y2={yReal} className="stroke-warn" strokeWidth={1} strokeDasharray="3 3" />
        <text x={LINE_X1} y={yReal + (isLong ? 12 : -5)} className="fill-warn text-[10px]">
          实际强平(更早)
        </text>

        {/* 爆仓价线 */}
        <line x1={LINE_X1} y1={yLiq} x2={LINE_X2} y2={yLiq} className="stroke-midas-red" strokeWidth={2} />
        <circle cx={LINE_X1} cy={yLiq} r={3.5} className="fill-midas-red" />
        <text x={LINE_X2} y={yLiq + (isLong ? 14 : -6)} textAnchor="end" className="fill-midas-red font-tabular text-[11px] font-semibold">
          理论爆仓价 ≈ {liq.toFixed(1)}
        </text>
      </svg>

      <div className="mt-3 space-y-2 text-sm">
        <p className="text-foreground/85">
          当前{isLong ? '多单' : '空单'} · 杠杆{' '}
          <span className="font-tabular font-semibold text-midas-red">{leverage}x</span> · 理论爆仓价{' '}
          <span className="font-tabular font-semibold text-midas-red">{liq.toFixed(1)}</span>(距开仓价{' '}
          <span className="font-tabular">{buffer.toFixed(1)}%</span>,即容错空间)。
        </p>
        <p className="text-foreground/60">
          {isLong ? '多单爆仓价在开仓价下方' : '空单爆仓价在开仓价上方'};杠杆越高,爆仓价越贴近开仓价、容错越小。
          {leverage === 1 ? '(1x:理论上价格归零才爆仓)' : null}
        </p>
        <div className="rounded border border-midas-red/30 bg-midas-red/5 px-3 py-2 text-[13px] leading-relaxed text-foreground/90">
          ⚠ 杠杆放大收益的同时<strong className="text-midas-red">同等放大亏损、可能爆仓</strong>。止损应设在爆仓价<strong>之前</strong>(更靠近开仓价的一侧)。
        </div>
        <p className="text-xs text-foreground/55">
          虚线为「实际强平」:因维持保证金 + 手续费 / 资金费 / 滑点,真实强平比理论爆仓价更早触发。
        </p>
      </div>
    </InteractiveCard>
  )
}
