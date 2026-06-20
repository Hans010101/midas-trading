'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { mergeKline, type Direction } from './kline-merge.calc'

const K1 = { high: 10, low: 3 }
const K2 = { high: 8, low: 5 }
const PMIN = 2
const PMAX = 11
const TOP = 24
const BOT = 176
const py = (p: number) => TOP + ((PMAX - p) / (PMAX - PMIN)) * (BOT - TOP)

export function KlineMergeDemo() {
  const [dir, setDir] = useState<Direction>('up')
  const m = mergeKline(K1, K2, dir)
  const btn = (active: boolean) =>
    'rounded border px-3 py-1 text-xs transition-colors ' +
    (active ? 'border-midas-red bg-surface-subtle text-midas-red' : 'border-paper text-foreground/70 hover:bg-surface-subtle')

  return (
    <InteractiveCard
      title="K线合并(缠论包含处理)"
      subtitle="两根有包含关系的 K 线,切换处理方向:向上取「高高」、向下取「低低」。"
    >
      <div className="mb-3 flex gap-2">
        <button type="button" onClick={() => setDir('up')} className={btn(dir === 'up')}>向上处理(取高高)</button>
        <button type="button" onClick={() => setDir('down')} className={btn(dir === 'down')}>向下处理(取低低)</button>
      </div>
      <svg viewBox="0 0 520 210" className="h-auto w-full select-none" role="img" aria-label="K线包含处理:K1包含K2,合并为一根新K线">
        <defs>
          <marker id="d14arrow" markerWidth={7} markerHeight={7} refX={6} refY={3} orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" className="fill-foreground/45" />
          </marker>
        </defs>
        {[2, 5, 8, 11].map((p) => (
          <g key={p}>
            <line x1={34} y1={py(p)} x2={486} y2={py(p)} className="stroke-foreground/15" strokeWidth={1} strokeDasharray="2 3" />
            <text x={28} y={py(p) + 4} textAnchor="end" className="fill-foreground/45 font-tabular text-[11px]">{p}</text>
          </g>
        ))}
        <rect x={70} y={py(K1.high)} width={30} height={py(K1.low) - py(K1.high)} rx={3} className="fill-surface-subtle stroke-foreground/40" strokeWidth={1.5} />
        <text x={85} y={py(K1.high) - 6} textAnchor="middle" className="fill-foreground/60 text-[12px]">K1</text>
        <rect x={120} y={py(K2.high)} width={30} height={py(K2.low) - py(K2.high)} rx={3} className="fill-paper stroke-foreground/40" strokeWidth={1.5} />
        <text x={135} y={py(K2.low) + 14} textAnchor="middle" className="fill-foreground/60 text-[12px]">K2</text>
        <text x={102} y={196} textAnchor="middle" className="fill-foreground/45 text-[11px]">K1 包含 K2</text>
        <line x1={200} y1={100} x2={248} y2={100} className="stroke-foreground/45" strokeWidth={1.5} markerEnd="url(#d14arrow)" />
        <text x={224} y={90} textAnchor="middle" className="fill-foreground/60 text-[11px]">{dir === 'up' ? '向上' : '向下'}</text>
        <rect x={360} y={py(m.high)} width={30} height={py(m.low) - py(m.high)} rx={3} className="fill-midas-red stroke-midas-red" strokeWidth={1.5} fillOpacity={0.1} />
        <text x={375} y={py(m.high) - 6} textAnchor="middle" className="fill-midas-red text-[12px]">合并后</text>
        <text x={375} y={196} textAnchor="middle" className="fill-midas-red font-tabular text-[11px]">高 {m.high} · 低 {m.low}</text>
      </svg>
      <div className="mt-2 rounded bg-surface-subtle px-3 py-2 text-sm text-foreground/85">
        {dir === 'up' ? (
          <>向上处理:高点取高者 max(10,8)=<span className="font-semibold text-midas-red">10</span>、低点也取高者 max(3,5)=<span className="font-semibold text-midas-red">5</span> → 合并 K(高10 低5)。</>
        ) : (
          <>向下处理:高点取低者 min(10,8)=<span className="font-semibold text-midas-red">8</span>、低点取低者 min(3,5)=<span className="font-semibold text-midas-red">3</span> → 合并 K(高8 低3)。</>
        )}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        包含关系 = 一根K线的高低点完全被相邻K线包住。<strong className="text-foreground/80">向上处理取「高高」</strong>(高点取高者、低点也取高者);<strong className="text-foreground/80">向下处理取「低低」</strong>。合并让后续分型、笔的判断更干净。
      </p>
    </InteractiveCard>
  )
}
