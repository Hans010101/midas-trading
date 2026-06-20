'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { detectFractals, buildBi } from './fractal-bi.calc'

const EX = [
  { highs: [5, 7, 9, 7, 5, 7, 9, 7, 5], lows: [2, 4, 6, 4, 2, 4, 6, 4, 2] },
  { highs: [8, 6, 4, 6, 8, 6, 4, 6, 8], lows: [5, 3, 1, 3, 5, 3, 1, 3, 5] },
]
const PMIN = 0
const PMAX = 10
const TOP = 24
const BOT = 180
const L = 46
const R = 486
const px = (i: number, n: number) => L + (i / (n - 1)) * (R - L)
const py = (p: number) => TOP + ((PMAX - p) / (PMAX - PMIN)) * (BOT - TOP)

export function FractalBiDemo() {
  const [cur, setCur] = useState(0)
  const { highs, lows, fractals, bis } = useMemo(() => {
    const d = EX[cur]
    const ks = d.highs.map((h, i) => ({ high: h, low: d.lows[i] }))
    const fr = detectFractals(ks)
    return { highs: d.highs, lows: d.lows, fractals: fr, bis: buildBi(fr) }
  }, [cur])
  const n = highs.length

  return (
    <InteractiveCard
      title="分型与笔(缠论)"
      subtitle="顶分型=中间K高低点都最高,底分型=都最低,顶底交替连成笔。换一组看不同结构。"
    >
      <div className="mb-3 flex items-center gap-3">
        <button type="button" onClick={() => setCur((cur + 1) % EX.length)} className="rounded border border-paper px-3 py-1 text-xs text-foreground/70 transition-colors hover:bg-surface-subtle">换一组结构</button>
        <span className="text-xs text-foreground/60">示例 {cur + 1}/2 · {fractals.length} 个分型 · {bis.length} 笔</span>
      </div>
      <svg viewBox="0 0 520 230" className="h-auto w-full select-none" role="img" aria-label="K线序列的顶底分型与笔">
        {bis.map((b, k) => {
          const a = fractals.find((f) => f.index === b.fromIndex)!
          const c = fractals.find((f) => f.index === b.toIndex)!
          const ay = a.type === 'top' ? py(highs[a.index]) : py(lows[a.index])
          const cy = c.type === 'top' ? py(highs[c.index]) : py(lows[c.index])
          return <line key={k} x1={px(a.index, n)} y1={ay} x2={px(c.index, n)} y2={cy} className="stroke-gold" strokeWidth={2} />
        })}
        {highs.map((h, i) => (
          <rect key={i} x={px(i, n) - 7} y={py(h)} width={14} height={py(lows[i]) - py(h)} rx={2} className="fill-surface-subtle stroke-foreground/30" strokeWidth={1} />
        ))}
        {fractals.map((f) =>
          f.type === 'top' ? (
            <g key={f.index}>
              <text x={px(f.index, n)} y={py(highs[f.index]) - 8} textAnchor="middle" className="fill-midas-red text-[13px]">▲</text>
              <text x={px(f.index, n)} y={py(highs[f.index]) - 20} textAnchor="middle" className="fill-midas-red text-[11px]">顶</text>
            </g>
          ) : (
            <g key={f.index}>
              <text x={px(f.index, n)} y={py(lows[f.index]) + 18} textAnchor="middle" className="fill-bear text-[13px]">▼</text>
              <text x={px(f.index, n)} y={py(lows[f.index]) + 30} textAnchor="middle" className="fill-bear text-[11px]">底</text>
            </g>
          ),
        )}
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-foreground/60">
        <span className="text-midas-red">▲ 顶分型</span>
        <span className="text-bear">▼ 底分型</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-gold align-middle" /> 笔</span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        <strong className="text-foreground/80">顶分型</strong> = 中间一根K的高点与低点都最高;<strong className="text-foreground/80">底分型</strong> = 都最低。<strong className="text-foreground/80">笔</strong> = 相邻顶底分型交替连接。分型与笔是结构骨架,不是买卖信号。
      </p>
    </InteractiveCard>
  )
}
