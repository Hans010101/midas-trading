'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { crossLiqPrice, crossMaxLoss, isolatedLiqPrice, isolatedMaxLoss, type MarginMode } from './margin-mode.calc'
import { linearScale } from './use-svg-drag'

const ENTRY = 100
const POS_MARGIN = 100
const ACCOUNT = 300
const VB_W = 360
const VB_H = 260
const PLOT_TOP = 24
const PLOT_BOTTOM = 224
const X1 = 96
const X2 = 322
const AXIS_X = 80
const P_MIN = 0
const P_MAX = 110

const priceToY = (p: number) => linearScale(p, P_MIN, P_MAX, PLOT_BOTTOM, PLOT_TOP)

export function MarginModeDemo() {
  const [mode, setMode] = useState<MarginMode>('isolated')
  const [leverage, setLeverage] = useState(10)

  const isoLiq = isolatedLiqPrice('long', leverage, ENTRY)
  const crossLiq = crossLiqPrice('long', leverage, ENTRY, POS_MARGIN, ACCOUNT)
  const isIso = mode === 'isolated'

  const yEntry = priceToY(ENTRY)
  const yIso = priceToY(Math.max(P_MIN, isoLiq))
  const yCross = priceToY(Math.max(P_MIN, crossLiq))
  const activeLiq = isIso ? isoLiq : crossLiq
  const maxLoss = isIso ? isolatedMaxLoss(POS_MARGIN) : crossMaxLoss(ACCOUNT)

  return (
    <InteractiveCard
      title="全仓 vs 逐仓"
      subtitle={`多单、开仓价 100、该仓保证金 ${POS_MARGIN}、账户总余额 ${ACCOUNT}。切换模式,看爆仓价与亏损边界的差别。`}
    >
      <div className="mb-4 inline-flex overflow-hidden rounded border border-paper">
        {(['isolated', 'cross'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            aria-pressed={mode === m}
            className={
              'px-4 py-1.5 text-sm font-medium transition-colors ' +
              (mode === m ? 'bg-midas-red text-white' : 'bg-surface-card text-foreground/60 hover:text-foreground')
            }
          >
            {m === 'isolated' ? '逐仓' : '全仓'}
          </button>
        ))}
      </div>
      <label className="mb-3 flex items-center gap-3 text-sm">
        <span className="shrink-0 text-foreground/60">杠杆</span>
        <input type="range" min={1} max={50} step={1} value={leverage}
          onChange={(e) => setLeverage(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="杠杆倍数" />
        <span className="w-12 shrink-0 text-right font-tabular font-semibold text-midas-red">{leverage}x</span>
      </label>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="h-auto w-full select-none" role="img" aria-label="逐仓与全仓爆仓价对比">
        <line x1={AXIS_X} y1={PLOT_TOP} x2={AXIS_X} y2={PLOT_BOTTOM} className="stroke-foreground/20" strokeWidth={1} />
        {[0, 25, 50, 75, 100].map((p) => (
          <g key={p}>
            <line x1={AXIS_X - 4} y1={priceToY(p)} x2={AXIS_X} y2={priceToY(p)} className="stroke-foreground/20" strokeWidth={1} />
            <text x={AXIS_X - 8} y={priceToY(p) + 4} textAnchor="end" className="fill-foreground/55 font-tabular text-[11px]">{p}</text>
          </g>
        ))}

        {/* 开仓价 */}
        <line x1={X1} y1={yEntry} x2={X2} y2={yEntry} className="stroke-foreground" strokeWidth={1.5} />
        <text x={X2} y={yEntry - 6} textAnchor="end" className="fill-foreground text-[11px]">开仓价 100</text>

        {/* 逐仓爆仓价 */}
        <line x1={X1} y1={yIso} x2={X2} y2={yIso} className="stroke-midas-red" strokeWidth={isIso ? 2.5 : 1} strokeDasharray={isIso ? undefined : '4 3'} opacity={isIso ? 1 : 0.5} />
        <text x={X1} y={yIso - 5} className="fill-midas-red font-tabular text-[11px] font-semibold" opacity={isIso ? 1 : 0.5}>逐仓爆仓 {isoLiq.toFixed(0)}</text>

        {/* 全仓爆仓价 */}
        <line x1={X1} y1={yCross} x2={X2} y2={yCross} className="stroke-midas-red-deep" strokeWidth={!isIso ? 2.5 : 1} strokeDasharray={!isIso ? undefined : '4 3'} opacity={!isIso ? 1 : 0.5} />
        <text x={X1} y={yCross + 13} className="fill-midas-red-deep font-tabular text-[11px] font-semibold" opacity={!isIso ? 1 : 0.5}>
          全仓爆仓 {crossLiq <= P_MIN ? '价格归零也不爆' : crossLiq.toFixed(0)}
        </text>
      </svg>

      <div className="mt-3 rounded bg-surface-subtle px-3 py-2 text-sm text-foreground/85">
        当前<strong className="text-midas-red">{isIso ? '逐仓' : '全仓'}</strong> · 爆仓价{' '}
        <span className="font-tabular font-semibold text-midas-red">
          {activeLiq <= P_MIN ? '——(账户余额足以扛到价格归零)' : activeLiq.toFixed(1)}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <div className={'rounded border px-3 py-2 ' + (isIso ? 'border-midas-red/30 bg-midas-red/5' : 'border-paper bg-surface-subtle/40')}>
          <div className="text-xs text-foreground/60">逐仓最大亏损</div>
          <div className="mt-0.5 font-tabular font-semibold text-foreground">{isolatedMaxLoss(POS_MARGIN)}(限于该仓)</div>
        </div>
        <div className={'rounded border px-3 py-2 ' + (!isIso ? 'border-midas-red/30 bg-midas-red/5' : 'border-paper bg-surface-subtle/40')}>
          <div className="text-xs text-foreground/60">全仓最大亏损</div>
          <div className="mt-0.5 font-tabular font-semibold text-foreground">{crossMaxLoss(ACCOUNT)}(整个账户)</div>
        </div>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        逐仓把亏损<strong className="text-foreground/80">隔离在该仓保证金</strong>内、爆仓只损失这一仓;全仓用<strong className="text-foreground/80">整个账户余额</strong>抵抗,爆仓价更远、但一旦爆仓影响全部资金。当前亏损边界 {maxLoss}。
      </p>
    </InteractiveCard>
  )
}
