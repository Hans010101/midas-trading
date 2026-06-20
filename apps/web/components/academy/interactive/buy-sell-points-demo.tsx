'use client'

import { InteractiveCard } from './interactive-card'
import { classifyBuy2, classifyBuy3 } from './buy-sell-points.calc'

const N = 24
const PMIN = 92
const PMAX = 116
const TOP = 18
const BOT = 180
const L = 40
const R = 470
const px = (i: number) => L + (i / (N - 1)) * (R - L)
const py = (p: number) => TOP + ((PMAX - p) / (PMAX - PMIN)) * (BOT - TOP)
const price = (i: number) => {
  if (i <= 5) return 110 - 3 * i
  if (i <= 9) return 95 + 2.75 * (i - 5)
  if (i <= 12) return 106 - 2.333 * (i - 9)
  if (i <= 16) return 99 + 2.75 * (i - 12)
  if (i <= 19) return 110 - 1.333 * (i - 16)
  return 106 + 2 * (i - 19)
}

const POINTS = [
  { i: 5, label: '1买', note: '下跌背驰末端', below: true },
  { i: 12, label: classifyBuy2(99, 95) === 'buy2' ? '2买' : '—', note: '回调不破前低', below: true },
  { i: 19, label: classifyBuy3(106, 104) === 'buy3' ? '3买' : '—', note: '回踩不破 ZG', below: false },
]

export function BuySellPointsDemo() {
  const prices = Array.from({ length: N }, (_, i) => price(i))
  const pts = prices.map((p, i) => `${px(i).toFixed(1)},${py(p).toFixed(1)}`).join(' ')

  return (
    <InteractiveCard
      title="买卖点(缠论)"
      subtitle="一二三类买点的结构位置;卖点对称。这是结构描述,不是买卖指令。"
    >
      <div className="mb-4 rounded border border-midas-red/40 bg-midas-red/10 px-3.5 py-2.5">
        <span className="text-sm font-semibold leading-relaxed text-midas-red-deep">买卖点是缠论对结构位置的描述,是结构术语,不是买卖指令 —— 会失败 · 不预测 · 不保证盈利</span>
      </div>
      <svg viewBox="0 0 520 210" className="h-auto w-full select-none" role="img" aria-label="价格走势上的一二三类买点结构位置与中枢">
        <rect x={px(8)} y={py(104)} width={px(15) - px(8)} height={py(99) - py(104)} rx={2} className="fill-gold stroke-gold" strokeWidth={1} fillOpacity={0.1} strokeDasharray="3 2" />
        <text x={px(11.5)} y={py(104) - 4} textAnchor="middle" className="fill-gold text-[10px]">中枢 ZG–ZD</text>
        <polyline points={pts} fill="none" className="stroke-foreground/60" strokeWidth={1.6} />
        {POINTS.map((p) => {
          const x = px(p.i)
          const y = py(prices[p.i])
          return (
            <g key={p.i}>
              <circle cx={x} cy={y} r={5} className="fill-midas-red" />
              <text x={x} y={y + (p.below ? 20 : -18)} textAnchor="middle" className="fill-midas-red text-[12px] font-semibold">{p.label}</text>
              <text x={x} y={y + (p.below ? 32 : -30)} textAnchor="middle" className="fill-foreground/45 text-[10px]">{p.note}</text>
            </g>
          )
        })}
      </svg>
      <p className="mt-2 text-xs leading-relaxed text-foreground/60">
        <strong className="text-foreground/80">一买</strong> = 下跌背驰末端;<strong className="text-foreground/80">二买</strong> = 一买后回调不破前低;<strong className="text-foreground/80">三买</strong> = 突破中枢后回踩不破中枢上沿 ZG。卖点对称。<span className="text-midas-red">这些是结构描述,出现买卖点不代表「该买」,任何买卖点都可能失败。</span>
      </p>
    </InteractiveCard>
  )
}
