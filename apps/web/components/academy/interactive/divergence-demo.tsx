'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { detectDivergence } from './divergence.calc'

const N = 30
const PMIN = 98
const PMAX = 124
const T1 = 18
const B1 = 128
const T2 = 150
const B2 = 236
const Z2 = 236
const L = 40
const R = 486
const px = (i: number) => L + (i / (N - 1)) * (R - L)
const py = (p: number) => T1 + ((PMAX - p) / (PMAX - PMIN)) * (B1 - T1)
const price = (i: number) => {
  if (i <= 8) return 100 + i * 1.875
  if (i <= 12) return 115 - (i - 8) * 1.75
  if (i <= 20) return 108 + (i - 12) * 1.5
  return 120 - (i - 20) * 0.9
}

export function DivergenceDemo() {
  const [mode, setMode] = useState<'yes' | 'no'>('yes')
  const { bars, kind } = useMemo(() => {
    const a1 = 8
    const a2 = mode === 'yes' ? 3.5 : 10
    const bars: number[] = []
    for (let i = 0; i < N; i++) {
      bars.push(a1 * Math.exp(-Math.pow((i - 6) / 3, 2)) + a2 * Math.exp(-Math.pow((i - 18) / 3, 2)))
    }
    return { bars, kind: detectDivergence(115, a1, 120, a2, 'high') }
  }, [mode])
  const prices = Array.from({ length: N }, (_, i) => price(i))
  const pricePts = prices.map((p, i) => `${px(i).toFixed(1)},${py(p).toFixed(1)}`).join(' ')
  const btn = (active: boolean) =>
    'rounded border px-3 py-1 text-xs transition-colors ' +
    (active ? 'border-midas-red bg-surface-subtle text-midas-red' : 'border-paper text-foreground/70 hover:bg-surface-subtle')

  return (
    <InteractiveCard
      title="背驰(缠论)"
      subtitle="价格创新高但 MACD 力度未同步创新高 = 顶背驰。切换看背驰 / 不背驰。"
    >
      <div className="mb-3 flex gap-2">
        <button type="button" onClick={() => setMode('yes')} className={btn(mode === 'yes')}>背驰(力度减弱)</button>
        <button type="button" onClick={() => setMode('no')} className={btn(mode === 'no')}>不背驰(力度增强)</button>
      </div>
      <svg viewBox="0 0 520 270" className="h-auto w-full select-none" role="img" aria-label="价格两峰与MACD两段力度对比">
        <polyline points={pricePts} fill="none" className="stroke-foreground/60" strokeWidth={1.6} />
        {[[8, '峰1'], [20, '峰2']].map(([i, lab]) => (
          <g key={i as number}>
            <line x1={px(i as number)} y1={py(prices[i as number]) - 4} x2={px(i as number)} y2={B1} className="stroke-foreground/25" strokeWidth={1} strokeDasharray="2 2" />
            <text x={px(i as number)} y={py(prices[i as number]) - 8} textAnchor="middle" className="fill-foreground/45 text-[11px]">{lab}</text>
          </g>
        ))}
        <text x={px(20)} y={py(120) - 22} textAnchor="middle" className="fill-midas-red text-[11px]">价格新高 ↑</text>
        {bars.map((h, i) => {
          const hh = (h / 12) * (B2 - T2)
          return hh > 0.5 ? <rect key={i} x={px(i) - 2.4} y={(Z2 - hh).toFixed(1)} width={4.8} height={hh.toFixed(1)} rx={1} className="fill-midas-red" fillOpacity={0.7} /> : null
        })}
        <line x1={L} y1={Z2} x2={R} y2={Z2} className="stroke-foreground/25" strokeWidth={1} />
        <text x={px(6)} y={T2 - 2} textAnchor="middle" className="fill-foreground/45 text-[11px]">段1 力度强</text>
        <text x={px(18)} y={mode === 'yes' ? T2 + 44 : T2 - 2} textAnchor="middle" className={mode === 'yes' ? 'fill-midas-red text-[11px]' : 'fill-foreground/45 text-[11px]'}>{mode === 'yes' ? '段2 力度弱' : '段2 力度更强'}</text>
        <text x={L - 6} y={T1 + 4} textAnchor="end" className="fill-foreground/45 text-[11px]">价</text>
        <text x={L - 6} y={T2 + 4} textAnchor="end" className="fill-foreground/45 text-[11px]">力</text>
      </svg>
      <div className={'mt-2 rounded px-3 py-2 text-sm ' + (kind === 'top' ? 'bg-midas-red/10 text-midas-red' : 'bg-surface-subtle text-foreground/70')}>
        {kind === 'top'
          ? <><strong className="font-semibold">顶背驰</strong>:价格峰2(120)＞ 峰1(115)创新高,但 MACD 段2 力度 ＜ 段1 → 动能衰减，不预示必然反转。</>
          : <><strong className="font-semibold">不背驰</strong>:价格创新高,MACD 段2 力度也增强(同步)→ 趋势动能未衰减,不构成背驰。</>}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        <strong className="text-foreground/80">背驰</strong> = 价格创新高(新低)但指标力度未同步创新高,趋势动能衰减。它是<strong className="text-foreground/80">力度比较、是参考</strong>,不是反转信号——背驰后可能盘整、可能反转,不保证、不预测。
      </p>
    </InteractiveCard>
  )
}
