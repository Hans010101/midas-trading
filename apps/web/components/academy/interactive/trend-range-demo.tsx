'use client'

import { useMemo, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { classifyMarket } from './trend-range.calc'

type Mode = 'up' | 'down' | 'range'
const DATA: Record<Mode, number[]> = {
  up: [96, 104, 99, 108, 102, 112, 105, 116],
  down: [116, 105, 112, 102, 108, 99, 104, 96],
  range: [100, 114, 99, 115, 101, 113, 100, 114],
}
const PMIN = 92
const PMAX = 120
const TOP = 18
const BOT = 170
const L = 44
const R = 486
const px = (i: number, n: number) => L + (i / (n - 1)) * (R - L)
const py = (p: number) => TOP + ((PMAX - p) / (PMAX - PMIN)) * (BOT - TOP)

const LABEL: Record<Mode, string> = { up: '上升趋势', down: '下降趋势', range: '震荡' }
const DESC: Record<Mode, React.ReactNode> = {
  up: <>高点 104→116、低点 96→105 都依次<strong className="font-semibold">抬高</strong> → 顺势(持有/回调找多),逆势高抛低吸易挨打。</>,
  down: <>高点 112→104、低点 105→96 都依次<strong className="font-semibold">降低</strong> → 顺势偏空,抄底逆势风险大。</>,
  range: <>高点约 114、低点约 100 <strong className="font-semibold">持平往返</strong> → 区间高抛低吸,追突破易假突破。</>,
}

export function TrendRangeDemo() {
  const [mode, setMode] = useState<Mode>('up')
  const { data, verdict } = useMemo(() => {
    const d = DATA[mode]
    const highs = d.filter((_, i) => i % 2 === 1)
    const lows = d.filter((_, i) => i % 2 === 0)
    return { data: d, verdict: classifyMarket(highs, lows) }
  }, [mode])
  const n = data.length
  const btn = (active: boolean) =>
    'rounded border px-3 py-1 text-xs transition-colors ' +
    (active ? 'border-midas-red bg-surface-subtle text-midas-red' : 'border-paper text-foreground/70 hover:bg-surface-subtle')
  const dashPts = (pickOdd: boolean) =>
    data.map((p, i) => ({ p, i })).filter((o) => (o.i % 2 === 1) === pickOdd).map((o) => `${px(o.i, n).toFixed(1)},${py(o.p).toFixed(1)}`).join(' ')

  return (
    <InteractiveCard
      title="趋势与震荡"
      subtitle="切换三种市态,看摆动高低点的结构差别。不同市态需要不同应对。"
    >
      <div className="mb-3 flex flex-wrap gap-2">
        <button type="button" onClick={() => setMode('up')} className={btn(mode === 'up')}>上升趋势</button>
        <button type="button" onClick={() => setMode('down')} className={btn(mode === 'down')}>下降趋势</button>
        <button type="button" onClick={() => setMode('range')} className={btn(mode === 'range')}>震荡</button>
      </div>
      <svg viewBox="0 0 520 210" className="h-auto w-full select-none" role="img" aria-label="不同市态下的价格走势与高低点">
        <polyline points={dashPts(true)} fill="none" className="stroke-gold" strokeWidth={1.3} strokeDasharray="4 3" />
        <polyline points={dashPts(false)} fill="none" className="stroke-gold" strokeWidth={1.3} strokeDasharray="4 3" />
        <polyline points={data.map((p, i) => `${px(i, n).toFixed(1)},${py(p).toFixed(1)}`).join(' ')} fill="none" className="stroke-foreground/60" strokeWidth={1.6} />
        {data.map((p, i) =>
          i % 2 === 1 ? (
            <text key={i} x={px(i, n)} y={py(p) - 8} textAnchor="middle" className="fill-midas-red text-[12px]">▲</text>
          ) : (
            <text key={i} x={px(i, n)} y={py(p) + 16} textAnchor="middle" className="fill-bear text-[12px]">▼</text>
          ),
        )}
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-foreground/60">
        <span className="text-midas-red">▲ 摆动高点</span>
        <span className="text-bear">▼ 摆动低点</span>
        <span><span className="inline-block h-0 w-4 border-t-2 border-dashed border-gold align-middle" /> 高/低点连线</span>
      </div>
      <div className="mt-2 rounded bg-surface-subtle px-3 py-2 text-sm text-foreground/85">
        判定:<strong className="font-semibold">{LABEL[verdict === 'uptrend' ? 'up' : verdict === 'downtrend' ? 'down' : 'range']}</strong> · {DESC[mode]}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        <strong className="text-foreground/80">上升趋势</strong> = 摆动高点与低点都依次抬高;<strong className="text-foreground/80">下降</strong> = 都降低;<strong className="text-foreground/80">震荡</strong> = 在区间内往返。不同市态适用不同方法,用错会反复挨打。市态判断是参考,事后清晰、事前难判。
      </p>
    </InteractiveCard>
  )
}
