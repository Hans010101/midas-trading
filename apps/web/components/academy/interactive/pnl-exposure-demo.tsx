'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { computePnl } from './pnl-exposure.calc'

const MARGIN = 1000

export function PnlExposureDemo() {
  const [leverage, setLeverage] = useState(10)
  const [movePct, setMovePct] = useState(-0.05)

  const r = computePnl(MARGIN, leverage, movePct)
  const gain = r.pnl >= 0
  const barShare = Math.min(1, Math.abs(r.pnlPctOfMargin))

  return (
    <InteractiveCard
      title="盈亏按名义敞口算,不是按保证金"
      subtitle={`保证金固定 ${MARGIN.toLocaleString()}。拖杠杆与价格变动,看小幅波动如何被名义敞口放大。`}
    >
      <div className="space-y-3">
        <label className="flex items-center gap-3 text-sm">
          <span className="w-20 shrink-0 text-foreground/60">杠杆</span>
          <input type="range" min={1} max={50} step={1} value={leverage}
            onChange={(e) => setLeverage(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="杠杆倍数" />
          <span className="w-14 shrink-0 text-right font-tabular font-semibold text-midas-red">{leverage}x</span>
        </label>
        <label className="flex items-center gap-3 text-sm">
          <span className="w-20 shrink-0 text-foreground/60">价格变动</span>
          <input type="range" min={-0.1} max={0.1} step={0.005} value={movePct}
            onChange={(e) => setMovePct(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="价格变动百分比" />
          <span className={'w-14 shrink-0 text-right font-tabular font-semibold ' + (gain ? 'text-up' : 'text-down')}>
            {(movePct * 100).toFixed(1)}%
          </span>
        </label>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-center text-sm">
        <div className="rounded border border-paper bg-surface-subtle/50 px-2 py-2">
          <div className="text-[11px] text-foreground/60">名义敞口 = 保证金 × 杠杆</div>
          <div className="mt-0.5 font-tabular font-semibold text-foreground">{r.notional.toLocaleString()}</div>
        </div>
        <div className="rounded border border-paper bg-surface-subtle/50 px-2 py-2">
          <div className="text-[11px] text-foreground/60">浮动盈亏 = 名义 × 变动%</div>
          <div className={'mt-0.5 font-tabular font-semibold ' + (gain ? 'text-up' : 'text-down')}>
            {r.pnl >= 0 ? '+' : ''}{r.pnl.toFixed(0)}
          </div>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        <div>
          <div className="mb-1 text-[11px] text-foreground/60">保证金 {MARGIN.toLocaleString()}</div>
          <div className="h-3 w-full rounded bg-foreground/15" />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-[11px] text-foreground/60">
            <span>浮动盈亏占保证金</span>
            <span className="font-tabular">{(r.pnlPctOfMargin * 100).toFixed(0)}%</span>
          </div>
          <div className="h-3 w-full overflow-hidden rounded bg-surface-subtle">
            <div
              className={'h-full ' + (r.liquidated ? 'bg-midas-red' : gain ? 'bg-up' : 'bg-down')}
              style={{ width: `${barShare * 100}%` }}
            />
          </div>
        </div>
      </div>

      <div
        className={
          'mt-3 rounded px-3 py-2 text-sm font-medium ' +
          (r.liquidated ? 'bg-midas-red/5 text-midas-red' : gain ? 'bg-success/10 text-success' : 'bg-warn/10 text-warn')
        }
      >
        {r.liquidated
          ? `⚠ 亏损已达 ${Math.abs(r.pnl).toFixed(0)} ≥ 保证金 ${MARGIN}:保证金被击穿、爆仓。仅 ${(movePct * 100).toFixed(1)}% 的反向波动就亏光了。`
          : gain
            ? `浮动盈利 ${r.pnl.toFixed(0)}(占保证金 ${(r.pnlPctOfMargin * 100).toFixed(0)}%)。`
            : `浮动亏损 ${Math.abs(r.pnl).toFixed(0)}(占保证金 ${Math.abs(r.pnlPctOfMargin * 100).toFixed(0)}%)。`}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        &ldquo;只投 1000 最多亏 1000&rdquo; 是<strong className="text-midas-red">致命误区</strong>:盈亏按名义敞口算,放大收益的同时<strong className="text-foreground/80">同等放大亏损</strong>,小幅反向 × 高杠杆即可击穿保证金而爆仓。
      </p>
    </InteractiveCard>
  )
}
