'use client'

import { useMemo, useRef, useState } from 'react'

import { InteractiveCard } from './interactive-card'
import { clampValue, linearScale, useVerticalDrag } from './use-svg-drag'
import { candleGeometry, clampHigh, clampLow, type CandleType, type OHLC } from './kline.calc'

const VB_W = 360
const VB_H = 300
const PLOT_TOP = 24
const PLOT_BOTTOM = 264
const P_MIN = 80
const P_MAX = 140
const CX = 180
const BODY_HALF = 26
const X_LEFT = 44
const X_RIGHT = VB_W - 12

const priceToY = (p: number) => linearScale(p, P_MIN, P_MAX, PLOT_BOTTOM, PLOT_TOP)
const yToPrice = (y: number) => linearScale(y, PLOT_BOTTOM, PLOT_TOP, P_MIN, P_MAX)

const PRESETS: { name: string; ohlc: OHLC }[] = [
  { name: '阳线', ohlc: { open: 100, high: 128, low: 95, close: 120 } },
  { name: '阴线', ohlc: { open: 120, high: 128, low: 92, close: 100 } },
  { name: '十字星', ohlc: { open: 110, high: 128, low: 92, close: 110 } },
]

const TYPE_LABEL: Record<CandleType, string> = {
  yang: '阳线(收 > 开)',
  yin: '阴线(收 < 开)',
  doji: '十字星(收 ≈ 开)',
}

// ★ 字面量 class（动态拼 `fill-${x}` 会被 Tailwind JIT 漏扫）；up/down 是 CSS 变量,不加透明度修饰
const STYLE: Record<CandleType, { stroke: string; bodyFill: string; text: string; chip: string; labelFill: string }> = {
  yang: { stroke: 'stroke-up', bodyFill: 'fill-surface-card', text: 'text-up', chip: 'bg-surface-subtle', labelFill: 'fill-up' },
  yin: { stroke: 'stroke-down', bodyFill: 'fill-down', text: 'text-down', chip: 'bg-surface-subtle', labelFill: 'fill-down' },
  doji: { stroke: 'stroke-ink-dim', bodyFill: 'fill-surface-card', text: 'text-ink-dim', chip: 'bg-surface-subtle', labelFill: 'fill-ink-dim' },
}

export function KlineAnatomyDemo() {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [ohlc, setOhlc] = useState<OHLC>(PRESETS[0].ohlc)

  const geo = useMemo(() => candleGeometry(ohlc), [ohlc])
  const s = STYLE[geo.type]
  const { open, high, low, close } = ohlc

  function handleMove(id: string, svgY: number) {
    const p = clampValue(Math.round(yToPrice(svgY)), P_MIN, P_MAX)
    setOhlc((prev) => {
      const next = { ...prev }
      if (id === 'open') next.open = p
      else if (id === 'close') next.close = p
      else if (id === 'high') next.high = p
      else if (id === 'low') next.low = p
      // 维持不变量:最高 ≥ 实体顶、最低 ≤ 实体底
      next.high = clampHigh(next.high, next.open, next.close)
      next.low = clampLow(next.low, next.open, next.close)
      return next
    })
  }
  const drag = useVerticalDrag({ svgRef, viewBoxHeight: VB_H, onMove: handleMove })

  const yTop = priceToY(geo.bodyTop)
  const yBottom = priceToY(geo.bodyBottom)
  const yH = priceToY(high)
  const yL = priceToY(low)

  const handles = [
    { id: 'high', cx: CX, cy: yH, label: '高' },
    { id: 'low', cx: CX, cy: yL, label: '低' },
    { id: 'open', cx: CX - BODY_HALF, cy: priceToY(open), label: '开' },
    { id: 'close', cx: CX + BODY_HALF, cy: priceToY(close), label: '收' },
  ]

  const readouts: [string, number][] = [
    ['开', open],
    ['高', high],
    ['低', low],
    ['收', close],
  ]

  return (
    <InteractiveCard
      title="一根 K 线是怎么构成的"
      subtitle="拖动 开 / 高 / 低 / 收 四个点,看实体与上下影线怎么变;或点预设切换阳线 / 阴线 / 十字星。"
    >
      <div className="mb-4 inline-flex overflow-hidden rounded border border-paper">
        {PRESETS.map((preset) => (
          <button
            key={preset.name}
            type="button"
            onClick={() => setOhlc(preset.ohlc)}
            className="border-r border-paper px-3 py-1.5 text-sm text-foreground/60 transition-colors last:border-r-0 hover:bg-surface-subtle hover:text-foreground"
          >
            {preset.name}
          </button>
        ))}
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        className="h-auto w-full select-none"
        onPointerMove={drag.onPointerMove}
        onPointerUp={drag.onPointerUp}
        onPointerCancel={drag.onPointerCancel}
        role="img"
        aria-label="K 线构成示意:拖动开高低收"
      >
        {[80, 95, 110, 125, 140].map((p) => (
          <g key={p}>
            <line x1={X_LEFT} y1={priceToY(p)} x2={X_RIGHT} y2={priceToY(p)} className="stroke-foreground/20" strokeWidth={0.5} strokeDasharray="2 4" />
            <text x={X_LEFT - 4} y={priceToY(p) + 3} textAnchor="end" className="fill-foreground/55 font-tabular text-[10px]">
              {p}
            </text>
          </g>
        ))}

        {/* 影线 */}
        <line x1={CX} y1={yH} x2={CX} y2={yTop} className={s.stroke} strokeWidth={1.5} />
        <line x1={CX} y1={yBottom} x2={CX} y2={yL} className={s.stroke} strokeWidth={1.5} />

        {/* 实体 */}
        <rect
          x={CX - BODY_HALF}
          y={yTop}
          width={BODY_HALF * 2}
          height={Math.max(2, yBottom - yTop)}
          className={`${s.bodyFill} ${s.stroke}`}
          strokeWidth={1.5}
        />

        <text x={CX + 14} y={yH + 3} className="fill-foreground/55 text-[9px]">最高</text>
        <text x={CX + 14} y={yL + 3} className="fill-foreground/55 text-[9px]">最低</text>

        {/* 四个拖拽手柄(inline map) */}
        {handles.map((h) => (
          <g key={h.id}>
            <circle
              cx={h.cx}
              cy={h.cy}
              r={8}
              className={`cursor-ns-resize fill-surface-card ${s.stroke} ${drag.activeId === h.id ? 'stroke-2' : ''}`}
              strokeWidth={1.5}
              style={{ touchAction: 'none' }}
              onPointerDown={drag.onPointerDown(h.id)}
            />
            <text x={h.cx} y={h.cy + 3} textAnchor="middle" className={`pointer-events-none ${s.labelFill} text-[9px] font-bold`}>
              {h.label}
            </text>
          </g>
        ))}
      </svg>

      <div className="mt-3 grid grid-cols-4 gap-2 text-center text-sm">
        {readouts.map(([k, v]) => (
          <div key={k} className="rounded border border-paper bg-surface-subtle/50 py-1.5">
            <div className="text-[11px] text-foreground/60">{k}</div>
            <div className="font-tabular font-semibold text-foreground">{v}</div>
          </div>
        ))}
      </div>
      <div className={`mt-2 rounded px-3 py-2 text-sm font-medium ${s.chip} ${s.text}`}>
        当前:{TYPE_LABEL[geo.type]} · 实体 {geo.bodyBottom}~{geo.bodyTop} · 上影 {geo.upperShadow} · 下影 {geo.lowerShadow}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        实体由<strong className="text-foreground/80">开盘价、收盘价</strong>围成;上影线 = 实体顶到最高,下影线 = 实体底到最低。
        国内习惯:<strong className="text-up">阳线红</strong>、<strong className="text-down">阴线绿</strong>(若你在设置里选了「绿涨红跌」,这里会随之翻转)。
      </p>
    </InteractiveCard>
  )
}
