'use client'

import { useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { computeSizing } from './position-sizing.calc'

const EQUITY = 10000

export function PositionSizingDemo() {
  const [riskPct, setRiskPct] = useState(0.01)
  const [stopPct, setStopPct] = useState(0.05)
  const [leverage, setLeverage] = useState(10)

  const r = computeSizing(EQUITY, riskPct, stopPct, leverage)
  // 名义 vs 保证金 条形(名义满格,保证金按 1/杠杆 占比)
  const marginShare = Math.min(1, r.marginUsed / r.notional)

  return (
    <InteractiveCard
      title="1%风险法:杠杆不决定单笔亏损"
      subtitle={`账户权益固定 ${EQUITY.toLocaleString()}。先定风险%、止损幅度→反推该开多大仓位;再拖杠杆,看哪些变、哪些不变。`}
    >
      <div className="space-y-3">
        <label className="flex items-center gap-3 text-sm">
          <span className="w-20 shrink-0 text-foreground/60">单笔风险</span>
          <input type="range" min={0.005} max={0.03} step={0.005} value={riskPct}
            onChange={(e) => setRiskPct(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="单笔风险百分比" />
          <span className="w-14 shrink-0 text-right font-tabular text-foreground/80">{(riskPct * 100).toFixed(1)}%</span>
        </label>
        <label className="flex items-center gap-3 text-sm">
          <span className="w-20 shrink-0 text-foreground/60">止损幅度</span>
          <input type="range" min={0.01} max={0.2} step={0.01} value={stopPct}
            onChange={(e) => setStopPct(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="止损幅度百分比" />
          <span className="w-14 shrink-0 text-right font-tabular text-foreground/80">{(stopPct * 100).toFixed(0)}%</span>
        </label>
        <label className="flex items-center gap-3 text-sm">
          <span className="w-20 shrink-0 text-foreground/60">杠杆</span>
          <input type="range" min={1} max={50} step={1} value={leverage}
            onChange={(e) => setLeverage(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer accent-midas-red" aria-label="杠杆倍数" />
          <span className="w-14 shrink-0 text-right font-tabular font-semibold text-midas-red">{leverage}x</span>
        </label>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center text-sm">
        <div className="rounded border border-paper bg-surface-subtle/50 px-2 py-2">
          <div className="text-[11px] text-foreground/60">单笔最大亏损</div>
          <div className="mt-0.5 font-tabular font-semibold text-foreground">{r.maxLoss.toFixed(0)}</div>
          <div className="mt-0.5 text-[10px] text-success">杠杆无关</div>
        </div>
        <div className="rounded border border-paper bg-surface-subtle/50 px-2 py-2">
          <div className="text-[11px] text-foreground/60">应开名义仓位</div>
          <div className="mt-0.5 font-tabular font-semibold text-foreground">{r.notional.toFixed(0)}</div>
          <div className="mt-0.5 text-[10px] text-success">杠杆无关</div>
        </div>
        <div className="rounded border border-midas-red/30 bg-midas-red/5 px-2 py-2">
          <div className="text-[11px] text-foreground/60">占用保证金</div>
          <div className="mt-0.5 font-tabular font-semibold text-midas-red">{r.marginUsed.toFixed(0)}</div>
          <div className="mt-0.5 text-[10px] text-midas-red">杠杆相关</div>
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-1 flex justify-between text-[11px] text-foreground/60">
          <span>名义仓位 {r.notional.toFixed(0)}</span>
          <span>保证金仅占 1/{leverage}</span>
        </div>
        <div className="h-3 w-full overflow-hidden rounded bg-surface-subtle">
          <div className="h-full bg-midas-red" style={{ width: `${marginShare * 100}%` }} />
        </div>
      </div>

      <div
        className={
          'mt-3 rounded px-3 py-2 text-sm font-medium ' +
          (r.stopSafe ? 'bg-success/10 text-success' : 'bg-midas-red/5 text-midas-red')
        }
      >
        {r.stopSafe
          ? `✓ 止损幅度 ${(stopPct * 100).toFixed(0)}% < 爆仓距 ${(r.liqDistPct * 100).toFixed(0)}%:止损会先于爆仓触发。`
          : `⚠ 止损幅度 ${(stopPct * 100).toFixed(0)}% ≥ 爆仓距 ${(r.liqDistPct * 100).toFixed(0)}%:杠杆过高,止损还没触发就先爆仓了。`}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        拖杠杆时,<strong className="text-foreground/80">单笔最大亏损和名义仓位都不变</strong>——它们由风险%和止损幅度决定;杠杆只改变占用多少保证金。
      </p>
    </InteractiveCard>
  )
}
