'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { simulateGrid } from './grid-trading.calc'

const OSC = [110, 100, 110, 100, 110]
const DOWN = [110, 108, 106, 104, 102, 100]
const LV = [100, 102, 104, 106, 108, 110]
const PMIN = 98
const PMAX = 112
const TOP = 16
const BOT = 176
const L = 44
const R = 486
const px = (i: number, n: number) => L + (i / (n - 1)) * (R - L)
const py = (p: number) => TOP + ((PMAX - p) / (PMAX - PMIN)) * (BOT - TOP)

export function GridTradingDemo() {
  const [mode, setMode] = useState<'osc' | 'down'>('osc')
  const { data, r } = useMemo(() => {
    const d = mode === 'osc' ? OSC : DOWN
    return { data: d, r: simulateGrid(100, 110, 5, d) }
  }, [mode])
  const n = data.length
  const btn = (active: boolean) =>
    'rounded border px-3 py-1 text-xs transition-colors ' +
    (active ? 'border-midas-red bg-surface-subtle text-midas-red' : 'border-paper text-foreground/70 hover:bg-surface-subtle')

  return (
    <InteractiveCard
      title="网格交易"
      subtitle="切换市态看网格命运:震荡市来回穿格赚价差,单边下跌只买不卖、逐格套牢。"
    >
      <div className="mb-3 flex gap-2">
        <button type="button" onClick={() => setMode('osc')} className={btn(mode === 'osc')}>震荡市</button>
        <button type="button" onClick={() => setMode('down')} className={btn(mode === 'down')}>单边下跌</button>
      </div>
      <svg viewBox="0 0 520 210" className="h-auto w-full select-none" role="img" aria-label="网格线与价格走势上的买卖成交点">
        {LV.map((lv) => (
          <g key={lv}>
            <line x1={L} y1={py(lv)} x2={R} y2={py(lv)} className="stroke-foreground/15" strokeWidth={1} strokeDasharray="2 3" />
            <text x={L - 6} y={py(lv) + 4} textAnchor="end" className="fill-foreground/45 font-tabular text-[11px]">{lv}</text>
          </g>
        ))}
        <polyline points={data.map((p, i) => `${px(i, n).toFixed(1)},${py(p).toFixed(1)}`).join(' ')} fill="none" className="stroke-foreground/60" strokeWidth={1.6} />
        {r.trades.map((tr, k) => (
          <circle key={k} cx={px(tr.i, n)} cy={py(tr.price)} r={4} className={tr.type === 'buy' ? 'fill-bear' : 'fill-midas-red'} />
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-foreground/60">
        <span className="text-bear">● 买入(下穿格线)</span>
        <span className="text-midas-red">● 卖出(上穿格线)</span>
      </div>
      <div className={'mt-2 rounded px-3 py-2 text-sm ' + (mode === 'osc' ? 'bg-success/10 text-success' : 'bg-midas-red/10 text-midas-red')}>
        {mode === 'osc'
          ? <>震荡市:买入 {r.buys} 次、卖出 {r.sells} 次配对,实现价差收益 ≈ <strong className="font-semibold">+{r.realized}</strong>,持仓 {r.openLots} → 网格的理想场景。</>
          : <>单边下跌:买入 {r.buys} 次、卖出 <strong className="font-semibold">0</strong> 次,持仓 <strong className="font-semibold">{r.openLots}</strong> 手全部套牢(逐格浮亏加深)→ 网格的天敌。</>}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        <strong className="text-foreground/80">网格</strong> = 区间内分层挂买卖单,价格波动反复成交赚价差。<strong className="text-foreground/80">适合震荡市</strong>;单边行情(尤其单边下跌)是天敌——越买越套、逐格浮亏加深。网格不是稳赚,区间选错、趋势突破会亏。
      </p>
    </InteractiveCard>
  )
}
