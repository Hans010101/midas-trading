'use client'

import { useMemo, useRef, useState } from 'react'

import { computePivot } from './chan-pivot.calc'
import { InteractiveCard } from './interactive-card'
import { clampValue, linearScale, useVerticalDrag } from './use-svg-drag'

const VB_W = 360
const VB_H = 280
const PLOT_TOP = 24
const PLOT_BOTTOM = 240
const P_MIN = 70
const P_MAX = 150
const MIN_GAP = 4
const COLS = [94, 194, 294]
const X_LEFT = 40
const X_RIGHT = VB_W - 12

const priceToY = (p: number) => linearScale(p, P_MIN, P_MAX, PLOT_BOTTOM, PLOT_TOP)
const yToPrice = (y: number) => linearScale(y, PLOT_BOTTOM, PLOT_TOP, P_MIN, P_MAX)

function parseId(id: string): { seg: number; kind: 'high' | 'low' } {
  const [kind, seg] = id.split('-') as ['high' | 'low', string]
  return { kind, seg: Number(seg) }
}

export function ChanPivotDemo() {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [pts, setPts] = useState<{ highs: number[]; lows: number[] }>({
    highs: [125, 120, 128],
    lows: [95, 100, 98],
  })

  const { zg, zd, formed } = useMemo(() => computePivot(pts.highs, pts.lows), [pts])

  function handleMove(id: string, svgY: number) {
    const { kind, seg } = parseId(id)
    const price = Math.round(yToPrice(svgY))
    setPts((prev) => {
      const highs = [...prev.highs]
      const lows = [...prev.lows]
      if (kind === 'high') highs[seg] = clampValue(price, lows[seg] + MIN_GAP, P_MAX)
      else lows[seg] = clampValue(price, P_MIN, highs[seg] - MIN_GAP)
      return { highs, lows }
    })
  }

  const drag = useVerticalDrag({ svgRef, viewBoxHeight: VB_H, onMove: handleMove })
  const yZg = priceToY(zg)
  const yZd = priceToY(zd)

  return (
    <InteractiveCard
      title="缠论中枢怎么形成"
      subtitle="拖动三段走势各自的高点 / 低点(共 6 个点),看上沿 ZG、下沿 ZD 怎么算、三段有没有共同重叠区。"
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        className="h-auto w-full select-none"
        onPointerMove={drag.onPointerMove}
        onPointerUp={drag.onPointerUp}
        onPointerCancel={drag.onPointerCancel}
        role="img"
        aria-label="缠论中枢形成示意:拖动三段高低点"
      >
        {[70, 90, 110, 130, 150].map((p) => (
          <g key={p}>
            <line x1={X_LEFT} y1={priceToY(p)} x2={X_RIGHT} y2={priceToY(p)} className="stroke-foreground/20" strokeWidth={0.5} strokeDasharray="2 4" />
            <text x={X_LEFT - 4} y={priceToY(p) + 3} textAnchor="end" className="fill-foreground/55 font-tabular text-[10px]">
              {p}
            </text>
          </g>
        ))}

        {/* 中枢带(成立才画) */}
        {formed ? <rect x={X_LEFT} y={yZg} width={X_RIGHT - X_LEFT} height={yZd - yZg} className="fill-midas-red/10" /> : null}

        {/* 三段:竖线(段范围) */}
        {COLS.map((x, i) => (
          <line key={i} x1={x} y1={priceToY(pts.lows[i])} x2={x} y2={priceToY(pts.highs[i])} className="stroke-ink-dim" strokeWidth={2} />
        ))}

        {/* ZG 上沿(min 高) */}
        <line x1={X_LEFT} y1={yZg} x2={X_RIGHT} y2={yZg} className="stroke-midas-red" strokeWidth={1.5} strokeDasharray="5 3" />
        <text x={X_LEFT + 4} y={yZg - 4} className="fill-midas-red font-tabular text-[10px] font-semibold">ZG 上沿 {zg}</text>

        {/* ZD 下沿(max 低) */}
        <line x1={X_LEFT} y1={yZd} x2={X_RIGHT} y2={yZd} className="stroke-midas-red-deep" strokeWidth={1.5} strokeDasharray="5 3" />
        <text x={X_LEFT + 4} y={yZd + 12} className="fill-midas-red-deep font-tabular text-[10px] font-semibold">ZD 下沿 {zd}</text>

        {/* 6 个拖拽手柄(inline map,不定义内联组件) */}
        {COLS.map((x, i) => (
          <g key={i}>
            <circle
              cx={x}
              cy={priceToY(pts.highs[i])}
              r={7}
              className={'cursor-ns-resize fill-surface-card stroke-midas-red ' + (drag.activeId === `high-${i}` ? 'stroke-2' : '')}
              strokeWidth={1.5}
              style={{ touchAction: 'none' }}
              onPointerDown={drag.onPointerDown(`high-${i}`)}
            />
            <text x={x} y={priceToY(pts.highs[i]) + 3} textAnchor="middle" className="pointer-events-none fill-midas-red text-[8px] font-bold">
              高{i + 1}
            </text>
            <circle
              cx={x}
              cy={priceToY(pts.lows[i])}
              r={7}
              className={'cursor-ns-resize fill-surface-card stroke-midas-red-deep ' + (drag.activeId === `low-${i}` ? 'stroke-2' : '')}
              strokeWidth={1.5}
              style={{ touchAction: 'none' }}
              onPointerDown={drag.onPointerDown(`low-${i}`)}
            />
            <text x={x} y={priceToY(pts.lows[i]) + 3} textAnchor="middle" className="pointer-events-none fill-midas-red-deep text-[8px] font-bold">
              低{i + 1}
            </text>
          </g>
        ))}
      </svg>

      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded border border-paper bg-surface-subtle/50 px-3 py-2">
          <div className="text-xs text-foreground/60">
            上沿 ZG = 三段高点的<strong className="text-midas-red">最小值</strong>
          </div>
          <div className="mt-1 font-tabular text-foreground/90">
            min({pts.highs.join(', ')}) = <strong className="text-midas-red">{zg}</strong>
          </div>
        </div>
        <div className="rounded border border-paper bg-surface-subtle/50 px-3 py-2">
          <div className="text-xs text-foreground/60">
            下沿 ZD = 三段低点的<strong className="text-midas-red-deep">最大值</strong>
          </div>
          <div className="mt-1 font-tabular text-foreground/90">
            max({pts.lows.join(', ')}) = <strong className="text-midas-red-deep">{zd}</strong>
          </div>
        </div>
      </div>
      <div className={'mt-2 rounded px-3 py-2 text-sm font-medium ' + (formed ? 'bg-success/10 text-success' : 'bg-warn/10 text-warn')}>
        {formed
          ? `✓ 构成中枢(ZD ${zd} < ZG ${zg},三段有共同重叠区 ${zd}~${zg})`
          : `✗ 不构成中枢(ZD ${zd} ≥ ZG ${zg},三段没有共同重叠区,只是依次运行)`}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        最易记反的就是取值方向:<strong className="text-foreground/80">上沿取最小、下沿取最大</strong>。中枢是三段走势的「共同重叠区」,不是简单的最高到最低。
      </p>
    </InteractiveCard>
  )
}
