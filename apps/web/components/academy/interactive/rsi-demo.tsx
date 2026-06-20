'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { computeRsi, isBlunted, type Zone } from './rsi.calc'

const N = 50
const PER = 14
const VB_W = 360
const VB_H = 250
const PADL = 30
const PADR = 10
const PT = 14
const PB = 120
const RT = 150
const RB = 234
const ix = (i: number) => PADL + (i / (N - 1)) * (VB_W - PADL - PADR)
const ry = (v: number) => RB - (v / 100) * (RB - RT)

function maxRun(rsi: (number | null)[], th: number, zone: Zone): number {
  let run = 0
  let mx = 0
  for (const r of rsi) {
    if (r == null) {
      run = 0
      continue
    }
    const inZone = zone === 'overbought' ? r >= th : r <= th
    if (inZone) {
      run++
      mx = Math.max(mx, run)
    } else {
      run = 0
    }
  }
  return mx
}

export function RsiDemo() {
  const [trend, setTrend] = useState(0.6)
  const { closes, rsi, priceLo, priceHi, obRun, osRun } = useMemo(() => {
    const c = Array.from({ length: N }, (_, i) => 100 + trend * i * 1.1 + 5 * Math.sin(i * 0.55))
    const r = computeRsi(c, PER)
    let lo = Infinity
    let hi = -Infinity
    c.forEach((v) => {
      lo = Math.min(lo, v)
      hi = Math.max(hi, v)
    })
    const pad = (hi - lo) * 0.1 || 1
    return { closes: c, rsi: r, priceLo: lo - pad, priceHi: hi + pad, obRun: maxRun(r, 70, 'overbought'), osRun: maxRun(r, 30, 'oversold') }
  }, [trend])
  const py = (p: number) => PB - ((p - priceLo) / (priceHi - priceLo)) * (PB - PT)
  const pricePts = closes.map((c, i) => `${ix(i).toFixed(1)},${py(c).toFixed(1)}`).join(' ')
  const rsiPts = rsi
    .map((v, i) => (v == null ? null : `${ix(i).toFixed(1)},${ry(v).toFixed(1)}`))
    .filter(Boolean)
    .join(' ')
  const label = trend > 0.15 ? '强涨' : trend < -0.15 ? '强跌' : '震荡'
  const blunted = isBlunted(rsi, 70, 5, 'overbought') ? 'ob' : isBlunted(rsi, 30, 5, 'oversold') ? 'os' : 'none'

  return (
    <InteractiveCard
      title="RSI 与钝化"
      subtitle="拖趋势强度,看强趋势中 RSI 长期贴在超买/超卖区钝化、不翻转。"
    >
      <label className="mb-3 flex items-center gap-3 text-sm">
        <span className="shrink-0 text-foreground/60">趋势强度</span>
        <input type="range" min={-1} max={1} step={0.1} value={trend}
          onChange={(e) => setTrend(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="趋势强度" />
        <span className={'w-16 shrink-0 text-right font-tabular font-semibold ' + (trend > 0.15 ? 'text-bull' : trend < -0.15 ? 'text-bear' : 'text-foreground/60')}>{label}</span>
      </label>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="h-auto w-full select-none" role="img" aria-label="价格与 RSI 曲线,超买超卖线">
        <polyline points={pricePts} fill="none" className="stroke-foreground/30" strokeWidth={1.4} />
        <rect x={PADL} y={ry(100)} width={VB_W - PADL - PADR} height={ry(70) - ry(100)} className="fill-bull" fillOpacity={0.05} />
        <rect x={PADL} y={ry(30)} width={VB_W - PADL - PADR} height={ry(0) - ry(30)} className="fill-bear" fillOpacity={0.05} />
        {[70, 30].map((v) => (
          <g key={v}>
            <line x1={PADL} y1={ry(v)} x2={VB_W - PADR} y2={ry(v)} className="stroke-foreground/20" strokeWidth={1} strokeDasharray="3 3" />
            <text x={PADL - 4} y={ry(v) + 3} textAnchor="end" className="fill-foreground/55 font-tabular text-[10px]">{v}</text>
          </g>
        ))}
        <polyline points={rsiPts} fill="none" className="stroke-midas-red" strokeWidth={1.8} />
      </svg>

      <div className="mt-2 flex flex-wrap gap-4 text-xs text-foreground/60">
        <span><span className="inline-block h-0 w-4 border-t-2 border-foreground/30 align-middle" /> 收盘价</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-midas-red align-middle" /> RSI</span>
        <span>虚线 = 70 / 30</span>
      </div>
      <div className={'mt-2 rounded px-3 py-2 text-sm ' + (blunted === 'ob' ? 'bg-midas-red/5 text-midas-red' : blunted === 'os' ? 'bg-success/10 text-success' : 'bg-surface-subtle text-foreground/70')}>
        {blunted === 'ob'
          ? `高位钝化:RSI 连续 ${obRun} 根贴在超买区(≥70)仍不反转——强势中超买 ≠ 卖点。`
          : blunted === 'os'
            ? `低位钝化:RSI 连续 ${osRun} 根贴在超卖区(≤30)仍不反转——弱势中超卖 ≠ 买点。`
            : '震荡行情:RSI 在 30~70 间往返,无明显钝化。'}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        超买(70)/超卖(30)是<strong className="text-foreground/80">参考、非反转信号</strong>。<strong className="text-midas-red">钝化</strong>:强趋势中 RSI 会长期贴在超买/超卖区,<strong className="text-foreground/80">不代表立即反转</strong>。
      </p>
    </InteractiveCard>
  )
}
