'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { computeKdj, detectKdjCrosses, isOverbought, isOversold } from './kdj.calc'

const N = 44
const PER = 9
const VB_W = 360
const VB_H = 230
const PADL = 30
const PADR = 10
const TOP = 14
const BOT = 214
const VMIN = -30
const VMAX = 130
const ix = (i: number) => PADL + (i / (N - 1)) * (VB_W - PADL - PADR)
const vy = (v: number) => BOT - ((v - VMIN) / (VMAX - VMIN)) * (BOT - TOP)
const linePts = (vals: number[]) => vals.map((v, i) => `${ix(i).toFixed(1)},${vy(v).toFixed(1)}`).join(' ')

export function KdjDemo() {
  const [trend, setTrend] = useState(0.7)
  const { points, golden, death, bluntRun, bluntZone, jOut } = useMemo(() => {
    const closes = Array.from({ length: N }, (_, i) => 100 + trend * i + 4 * Math.sin(i * 0.5))
    const highs = closes.map((c, i) => c + 1.5 + Math.abs(2 * Math.sin(i * 0.8)))
    const lows = closes.map((c, i) => c - 1.5 - Math.abs(2 * Math.sin(i * 0.8)))
    const pts = computeKdj(highs, lows, closes, PER)
    const crosses = detectKdjCrosses(pts)
    let obRun = 0
    let osRun = 0
    let obMax = 0
    let osMax = 0
    pts.forEach((p) => {
      if (isOverbought(p)) { obRun++; obMax = Math.max(obMax, obRun) } else obRun = 0
      if (isOversold(p)) { osRun++; osMax = Math.max(osMax, osRun) } else osRun = 0
    })
    const zone = obMax >= 4 ? 'ob' : osMax >= 4 ? 'os' : 'none'
    return {
      points: pts,
      golden: crosses.filter((c) => c.type === 'golden'),
      death: crosses.filter((c) => c.type === 'death'),
      bluntRun: zone === 'ob' ? obMax : osMax,
      bluntZone: zone,
      jOut: pts.some((p) => p.j > 100 || p.j < 0),
    }
  }, [trend])
  const label = trend > 0.15 ? '强涨' : trend < -0.15 ? '强跌' : '震荡'

  return (
    <InteractiveCard
      title="KDJ:K / D / J 三线"
      subtitle="拖趋势强度,看 K 上穿 D(金叉)、超买超卖区与钝化;J 最敏感、可冲出 0~100。固定参数 (9,3,3)。"
    >
      <label className="mb-3 flex items-center gap-3 text-sm">
        <span className="shrink-0 text-foreground/60">趋势强度</span>
        <input type="range" min={-1} max={1} step={0.1} value={trend}
          onChange={(e) => setTrend(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="趋势强度" />
        <span className={'w-16 shrink-0 text-right font-tabular font-semibold ' + (trend > 0.15 ? 'text-bull' : trend < -0.15 ? 'text-bear' : 'text-foreground/60')}>{label}</span>
      </label>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="h-auto w-full select-none" role="img" aria-label="KDJ 的 K D J 三线与超买超卖线">
        <rect x={PADL} y={vy(100)} width={VB_W - PADL - PADR} height={vy(80) - vy(100)} className="fill-bull" fillOpacity={0.05} />
        <rect x={PADL} y={vy(20)} width={VB_W - PADL - PADR} height={vy(0) - vy(20)} className="fill-bear" fillOpacity={0.05} />
        {[100, 80, 20, 0].map((v) => (
          <g key={v}>
            <line x1={PADL} y1={vy(v)} x2={VB_W - PADR} y2={vy(v)} className="stroke-foreground/15" strokeWidth={1} strokeDasharray={v === 80 || v === 20 ? '3 3' : undefined} />
            <text x={PADL - 4} y={vy(v) + 3} textAnchor="end" className="fill-foreground/50 font-tabular text-[10px]">{v}</text>
          </g>
        ))}
        <polyline points={linePts(points.map((p) => p.j))} fill="none" className="stroke-foreground/40" strokeWidth={1.2} />
        <polyline points={linePts(points.map((p) => p.d))} fill="none" className="stroke-gold" strokeWidth={1.6} />
        <polyline points={linePts(points.map((p) => p.k))} fill="none" className="stroke-midas-red" strokeWidth={1.6} />
        {golden.map((c) => (
          <circle key={`g${c.index}`} cx={ix(c.index)} cy={vy(points[c.index].k)} r={3.5} className="fill-bull" />
        ))}
        {death.map((c) => (
          <circle key={`d${c.index}`} cx={ix(c.index)} cy={vy(points[c.index].k)} r={3.5} className="fill-bear" />
        ))}
      </svg>

      <div className="mt-2 flex flex-wrap gap-4 text-xs text-foreground/60">
        <span><span className="inline-block h-0 w-4 border-t-2 border-midas-red align-middle" /> K</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-gold align-middle" /> D</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-foreground/40 align-middle" /> J</span>
        <span className="text-bull">● 金叉</span>
        <span className="text-bear">● 死叉</span>
      </div>
      <div className="mt-2 rounded bg-surface-subtle px-3 py-2 text-sm text-foreground/85">
        金叉 <span className="font-semibold text-bull">{golden.length}</span> 次 · 死叉 <span className="font-semibold text-bear">{death.length}</span> 次{jOut ? ' · J 已冲出 0~100(正常)' : ''}
      </div>
      {bluntZone !== 'none' && (
        <div className={'mt-2 rounded px-3 py-2 text-sm ' + (bluntZone === 'ob' ? 'bg-midas-red/5 text-midas-red' : 'bg-success/10 text-success')}>
          {bluntZone === 'ob'
            ? `高位钝化:K、D 连续 ${bluntRun} 根贴在超买区(>80)——强势中超买 ≠ 卖点。`
            : `低位钝化:K、D 连续 ${bluntRun} 根贴在超卖区(<20)——弱势中超卖 ≠ 买点。`}
        </div>
      )}
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        超买(&gt;80)/超卖(&lt;20)是<strong className="text-foreground/80">参考、非反转信号</strong>;强趋势会<strong className="text-midas-red">钝化</strong>。J = 3K − 2D 最敏感,<strong className="text-foreground/80">可冲出 0~100 属正常</strong>。KDJ 金叉、均线金叉、MACD 金叉是三个不同的「金叉」,别混。
      </p>
    </InteractiveCard>
  )
}
