'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { movingAverage, detectMaCrosses } from './moving-average.calc'

const N = 52
const LONG = 20
const CLOSES = Array.from({ length: N }, (_, i) => 100 + 18 * Math.sin(i * 0.3))
const VB_W = 360
const VB_H = 240
const PADL = 34
const PADR = 10
const TOP = 16
const BOT = 204
const PMIN = 80
const PMAX = 120
const ix = (i: number) => PADL + (i / (N - 1)) * (VB_W - PADL - PADR)
const py = (p: number) => BOT - ((p - PMIN) / (PMAX - PMIN)) * (BOT - TOP)
const linePts = (series: (number | null)[]) =>
  series
    .map((v, i) => (v == null ? null : `${ix(i).toFixed(1)},${py(v).toFixed(1)}`))
    .filter(Boolean)
    .join(' ')

export function MovingAverageDemo() {
  const [short, setShort] = useState(5)
  const { mS, mL, crosses } = useMemo(() => {
    const s = movingAverage(CLOSES, short)
    const l = movingAverage(CLOSES, LONG)
    return { mS: s, mL: l, crosses: detectMaCrosses(s, l) }
  }, [short])
  const golden = crosses.filter((c) => c.type === 'golden').length
  const death = crosses.filter((c) => c.type === 'death').length

  return (
    <InteractiveCard
      title="均线金叉 / 死叉"
      subtitle="拖短均线周期,看短均线上穿长均线(金叉)、下穿(死叉)。长均线固定 MA20。"
    >
      <label className="mb-3 flex items-center gap-3 text-sm">
        <span className="shrink-0 text-foreground/60">短均线 MA</span>
        <input type="range" min={3} max={12} step={1} value={short}
          onChange={(e) => setShort(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="短均线周期" />
        <span className="w-24 shrink-0 text-right font-tabular font-semibold">
          <span className="text-midas-red">MA{short}</span> × <span className="text-gold">MA20</span>
        </span>
      </label>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="h-auto w-full select-none" role="img" aria-label="价格与双均线,金叉死叉标记">
        <line x1={PADL} y1={TOP} x2={PADL} y2={BOT} className="stroke-foreground/20" strokeWidth={1} />
        {[80, 100, 120].map((p) => (
          <text key={p} x={PADL - 7} y={py(p) + 4} textAnchor="end" className="fill-foreground/55 font-tabular text-[11px]">{p}</text>
        ))}
        <polyline points={linePts(CLOSES)} fill="none" className="stroke-foreground/25" strokeWidth={1} />
        <polyline points={linePts(mL)} fill="none" className="stroke-gold" strokeWidth={1.8} />
        <polyline points={linePts(mS)} fill="none" className="stroke-midas-red" strokeWidth={1.8} />
        {crosses.map((c, k) => {
          const g = c.type === 'golden'
          const y = mS[c.index] as number
          return (
            <g key={k}>
              <circle cx={ix(c.index)} cy={py(y)} r={4} className={g ? 'fill-bull' : 'fill-bear'} />
              <text x={ix(c.index)} y={py(y) + (g ? -9 : 16)} textAnchor="middle"
                className={(g ? 'fill-bull' : 'fill-bear') + ' font-semibold text-[11px]'}>{g ? '金' : '死'}</text>
            </g>
          )
        })}
      </svg>

      <div className="mt-2 flex flex-wrap gap-4 text-xs text-foreground/60">
        <span><span className="inline-block h-0 w-4 border-t-2 border-midas-red align-middle" /> 短均线</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-gold align-middle" /> 长均线 MA20</span>
        <span className="text-bull">● 金叉</span>
        <span className="text-bear">● 死叉</span>
      </div>
      <div className="mt-2 rounded bg-surface-subtle px-3 py-2 text-sm text-foreground/85">
        当前 <span className="font-semibold text-midas-red">MA{short}</span> × <span className="font-semibold text-gold">MA20</span> · 金叉{' '}
        <span className="font-semibold text-bull">{golden}</span> 次 · 死叉 <span className="font-semibold text-bear">{death}</span> 次(参考、非交易指令)
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        这是<strong className="text-foreground/80">均线金叉</strong>:短均线上穿长均线(MA5 上穿 MA20)。<strong className="text-midas-red">≠ MACD 金叉</strong>——MACD 金叉是 DIF 上穿 DEA(两条派生线),不是价格均线。
      </p>
    </InteractiveCard>
  )
}
