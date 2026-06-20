'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { bollingerBands, bandwidth, stddev } from './bollinger.calc'

const N = 52
const PER = 20
const CLOSES = Array.from(
  { length: N },
  (_, i) => 100 + 12 * Math.sin(i * 0.28) + (i > 34 ? (i - 34) * 1.3 : 0) + 4 * Math.sin(i * 0.7),
)
const VB_W = 360
const VB_H = 240
const PADL = 34
const PADR = 10
const TOP = 16
const BOT = 204
const PMIN = 70
const PMAX = 130
const ix = (i: number) => PADL + (i / (N - 1)) * (VB_W - PADL - PADR)
const py = (p: number) => BOT - ((p - PMIN) / (PMAX - PMIN)) * (BOT - TOP)
const linePts = (series: (number | null)[]) =>
  series
    .map((v, i) => (v == null ? null : `${ix(i).toFixed(1)},${py(v).toFixed(1)}`))
    .filter(Boolean)
    .join(' ')

export function BollingerDemo() {
  const [k, setK] = useState(2)
  const { bands, fillPts, lastBw, lastDev } = useMemo(() => {
    const b = bollingerBands(CLOSES, PER, k)
    const sd = stddev(CLOSES, PER)
    const up: string[] = []
    const lo: string[] = []
    b.forEach((band, i) => {
      if (band.upper != null) up.push(`${ix(i).toFixed(1)},${py(band.upper).toFixed(1)}`)
    })
    for (let i = b.length - 1; i >= 0; i--) {
      const band = b[i]
      if (band.lower != null) lo.push(`${ix(i).toFixed(1)},${py(band.lower).toFixed(1)}`)
    }
    const li = N - 1
    return { bands: b, fillPts: up.concat(lo).join(' '), lastBw: bandwidth(b[li]), lastDev: sd[li] }
  }, [k])

  return (
    <InteractiveCard
      title="布林带:上下轨对称"
      subtitle="拖标准差倍数 K,看上下轨相对中轨对称张缩。中轨 = MA20。"
    >
      <label className="mb-3 flex items-center gap-3 text-sm">
        <span className="shrink-0 text-foreground/60">标准差倍数 K</span>
        <input type="range" min={1} max={3} step={0.5} value={k}
          onChange={(e) => setK(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="标准差倍数" />
        <span className="w-10 shrink-0 text-right font-tabular font-semibold text-midas-red">{k.toFixed(1)}</span>
      </label>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="h-auto w-full select-none" role="img" aria-label="价格与布林带上中下三轨">
        <line x1={PADL} y1={TOP} x2={PADL} y2={BOT} className="stroke-foreground/20" strokeWidth={1} />
        {[70, 100, 130].map((p) => (
          <text key={p} x={PADL - 7} y={py(p) + 4} textAnchor="end" className="fill-foreground/55 font-tabular text-[11px]">{p}</text>
        ))}
        {fillPts && <polygon points={fillPts} className="fill-midas-red" fillOpacity={0.06} stroke="none" />}
        <polyline points={linePts(CLOSES)} fill="none" className="stroke-foreground/25" strokeWidth={1} />
        <polyline points={linePts(bands.map((b) => b.upper))} fill="none" className="stroke-midas-red" strokeWidth={1.6} />
        <polyline points={linePts(bands.map((b) => b.lower))} fill="none" className="stroke-midas-red" strokeWidth={1.6} />
        <polyline points={linePts(bands.map((b) => b.mid))} fill="none" className="stroke-gold" strokeWidth={1.4} strokeDasharray="4 3" />
      </svg>

      <div className="mt-2 flex flex-wrap gap-4 text-xs text-foreground/60">
        <span><span className="inline-block h-0 w-4 border-t-2 border-midas-red align-middle" /> 上/下轨</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-dashed border-gold align-middle" /> 中轨 MA20</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-foreground/25 align-middle" /> 收盘价</span>
      </div>
      <div className="mt-2 rounded bg-surface-subtle px-3 py-2 text-sm text-foreground/85">
        K = <span className="font-semibold text-midas-red">{k.toFixed(1)}</span> · 上轨到中轨 = 中轨到下轨 ={' '}
        <span className="font-semibold">{lastDev != null ? (k * lastDev).toFixed(1) : '—'}</span>(对称)· 末根带宽{' '}
        <span className="font-semibold">{lastBw != null ? (lastBw * 100).toFixed(1) : '—'}%</span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        上轨 = 中轨 + K×σ、下轨 = 中轨 − K×σ,<strong className="text-foreground/80">上下对称(K=2)</strong>。触上轨<strong className="text-foreground/80">非必跌</strong>、触下轨非必涨——强趋势会沿轨运行(开口);带宽反映波动率。
      </p>
    </InteractiveCard>
  )
}
