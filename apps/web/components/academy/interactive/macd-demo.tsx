'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { computeMacd, detectMacdCrosses } from './macd.calc'

const N = 60
const SCENES = [
  Array.from({ length: N }, (_, i) => 100 + (i < 20 ? -i * 0.8 : (i - 20) * 0.9) + 3 * Math.sin(i * 0.5)),
  Array.from({ length: N }, (_, i) => 100 + i * 0.6 + 6 * Math.sin(i * 0.45)),
]
const VB_W = 360
const VB_H = 250
const PADL = 30
const PADR = 10
const LT = 14
const LB = 150
const HT = 160
const HB = 232
const ZERO = (HT + HB) / 2
const ix = (i: number) => PADL + (i / (N - 1)) * (VB_W - PADL - PADR)

export function MacdDemo() {
  const [scene, setScene] = useState(0)
  const { points, golden, death, lo, hi, hmax } = useMemo(() => {
    const pts = computeMacd(SCENES[scene])
    const crosses = detectMacdCrosses(pts)
    let mn = Infinity
    let mx = -Infinity
    let hm = 0
    for (let i = 26; i < N; i++) {
      mn = Math.min(mn, pts[i].dif, pts[i].dea)
      mx = Math.max(mx, pts[i].dif, pts[i].dea)
      hm = Math.max(hm, Math.abs(pts[i].hist))
    }
    const pad = (mx - mn) * 0.15 || 1
    return {
      points: pts,
      golden: crosses.filter((c) => c.type === 'golden'),
      death: crosses.filter((c) => c.type === 'death'),
      lo: mn - pad,
      hi: mx + pad,
      hmax: hm || 1,
    }
  }, [scene])
  const ly = (v: number) => LB - ((v - lo) / (hi - lo)) * (LB - LT)
  const hy = (v: number) => ZERO - (v / hmax) * ((HB - HT) / 2)
  const difPts = points.slice(26).map((p, k) => `${ix(k + 26).toFixed(1)},${ly(p.dif).toFixed(1)}`).join(' ')
  const deaPts = points.slice(26).map((p, k) => `${ix(k + 26).toFixed(1)},${ly(p.dea).toFixed(1)}`).join(' ')

  return (
    <InteractiveCard
      title="MACD 金叉(DIF 上穿 DEA)"
      subtitle="固定参数 EMA12 / EMA26 / DEA9。DIF 上穿 DEA = 金叉、下穿 = 死叉;柱 = (DIF − DEA) × 2。"
    >
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="text-foreground/60">固定标准参数 <strong className="text-foreground/80">12 / 26 / 9</strong></span>
        <button type="button" onClick={() => setScene((scene + 1) % 2)}
          className="rounded border border-paper px-3 py-1 text-xs text-foreground/70 transition-colors hover:bg-surface-subtle">
          切换示例 {scene + 1}/2
        </button>
      </div>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="h-auto w-full select-none" role="img" aria-label="MACD 的 DIF DEA 双线与柱状图">
        <line x1={PADL} y1={ly(0)} x2={VB_W - PADR} y2={ly(0)} className="stroke-foreground/20" strokeWidth={1} strokeDasharray="3 3" />
        <line x1={PADL} y1={ZERO} x2={VB_W - PADR} y2={ZERO} className="stroke-foreground/20" strokeWidth={1} />
        {points.slice(26).map((p, k) => {
          const i = k + 26
          const y = hy(p.hist)
          return (
            <rect key={i} x={ix(i) - 1.6} y={Math.min(ZERO, y)} width={3.2} height={Math.max(0.5, Math.abs(ZERO - y))}
              className={p.hist >= 0 ? 'fill-bull' : 'fill-bear'} opacity={0.85} />
          )
        })}
        <polyline points={difPts} fill="none" className="stroke-midas-red" strokeWidth={1.8} />
        <polyline points={deaPts} fill="none" className="stroke-gold" strokeWidth={1.8} />
        {golden.map((c) => (
          <g key={`g${c.index}`}>
            <circle cx={ix(c.index)} cy={ly(points[c.index].dif)} r={4} className="fill-bull" />
            <text x={ix(c.index)} y={ly(points[c.index].dif) - 8} textAnchor="middle" className="fill-bull font-semibold text-[11px]">金</text>
          </g>
        ))}
        {death.map((c) => (
          <circle key={`d${c.index}`} cx={ix(c.index)} cy={ly(points[c.index].dif)} r={4} className="fill-bear" />
        ))}
      </svg>

      <div className="mt-2 flex flex-wrap gap-4 text-xs text-foreground/60">
        <span><span className="inline-block h-0 w-4 border-t-2 border-midas-red align-middle" /> DIF</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-gold align-middle" /> DEA(信号线)</span>
        <span>柱 = (DIF − DEA) × 2</span>
      </div>
      <div className="mt-2 rounded bg-surface-subtle px-3 py-2 text-sm text-foreground/85">
        示例 {scene + 1}/2 · 金叉 <span className="font-semibold text-bull">{golden.length}</span> 次 · 死叉{' '}
        <span className="font-semibold text-bear">{death.length}</span> 次(参考、非交易指令)
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        <strong className="text-midas-red">MACD 金叉 = DIF 上穿 DEA</strong>(两条派生线),柱由绿转红 ≈ 金叉区。<strong className="text-foreground/80">不是均线、不是价格</strong>——和 D9 的均线金叉(MA5 上穿 MA20)是两个不同的「金叉」。
      </p>
    </InteractiveCard>
  )
}
