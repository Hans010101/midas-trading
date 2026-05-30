'use client'

/**
 * 世界地图视觉模块(ADR 0035 阶段 B · 纯前端视觉增强)。
 *
 * 读阶段 A 同一份 /overview/global 数据(主要股指),不新增后端、不碰数据层。
 * 渲染:点阵风格世界地图(Natural Earth 110m 采样 · 见 world-dots.ts)+ 各市场标记点 + 标签。
 *
 * 配色铁律(★ 与阶段 A 一致):涨跌严格复用 `--color-up` / `--color-down`(默认红涨绿跌),
 *   随用户偏好与卡片同步翻转 · 不引入任何设计稿独立配色变量。陆地点用中性冷灰(非暖色)。
 * 响应式:HTML 标签层叠在 SVG 上(不随 viewBox 缩放、始终清晰);窄屏隐藏密集区(东亚)次要标签,
 *   只留标记点,避免标签糊成一团(细节看下方卡片)。
 */

import { cn } from '@/lib/utils'

import { WORLD_DOTS } from './world-dots'

// 赤道矩形投影(与 world-dots 生成器同式)· viewBox 0 0 1000 500
function projX(lng: number): number {
  return ((lng + 180) / 360) * 1000
}
function projY(lat: number): number {
  return ((90 - lat) / 180) * 500
}

// 裁掉南极/远北空白(陆地点 lat 78..-56 → y 28..412)
const VB_X = 0
const VB_Y = 26
const VB_W = 1000
const VB_H = 388

// 陆地点中性冷灰(非暖粉褐 · 非缠论中枢专用色)· 对齐白底卡片的克制清爽
const LAND = '#c4ccd4'

/**
 * 市场地理配置(静态 · 前端)。symbol 对应阶段 A 数据里的指数。
 * (lx, ly) = 标签锚点(viewBox 单位)· 从标记点拉引导线到此,东亚密集区靠它防重叠。
 * priority 1 = 主要/地理孤立市场(窄屏也显示标签);2 = 密集区次要(窄屏只留点、隐藏标签)。
 */
type MarketGeo = {
  symbol: string
  short: string
  lng: number
  lat: number
  lx: number
  ly: number
  align: 'left' | 'right' | 'center'
  priority: 1 | 2
}

const MARKET_GEO: readonly MarketGeo[] = [
  { symbol: '^GSPC', short: '标普', lng: -74, lat: 40.7, lx: 250, ly: 196, align: 'center', priority: 1 },
  { symbol: '^FTSE', short: '富时', lng: -0.1, lat: 51.5, lx: 452, ly: 64, align: 'right', priority: 1 },
  { symbol: '^GDAXI', short: 'DAX', lng: 8.7, lat: 50.1, lx: 566, ly: 60, align: 'left', priority: 2 },
  { symbol: '^N225', short: '日经', lng: 139.7, lat: 35.7, lx: 930, ly: 118, align: 'right', priority: 1 },
  { symbol: '000001.SS', short: '上证', lng: 121.5, lat: 31.2, lx: 930, ly: 150, align: 'right', priority: 2 },
  { symbol: '^HSI', short: '恒生', lng: 114.2, lat: 22.3, lx: 930, ly: 182, align: 'right', priority: 2 },
]

export type MapQuote = { name: string; changePct: number }

type Marker = MarketGeo & { changePct: number; x: number; y: number }

export function WorldMap({ quotes }: { quotes: Map<string, MapQuote> }) {
  const markers: Marker[] = []
  for (const g of MARKET_GEO) {
    const q = quotes.get(g.symbol)
    if (!q) continue
    markers.push({ ...g, changePct: q.changePct, x: projX(g.lng), y: projY(g.lat) })
  }

  return (
    <div className="relative w-full overflow-hidden rounded-lg border border-paper bg-background">
      <svg
        viewBox={`${VB_X} ${VB_Y} ${VB_W} ${VB_H}`}
        className="block h-auto w-full"
        role="img"
        aria-label="全球主要股指地理分布"
      >
        {/* 陆地点阵(中性冷灰) */}
        <g fill={LAND}>
          {WORLD_DOTS.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={1.5} />
          ))}
        </g>
        {/* 引导线 + 标记点(红涨绿跌 · 复用 --color-up/down) */}
        {markers.map((m) => {
          const color = m.changePct >= 0 ? 'var(--color-up)' : 'var(--color-down)'
          // 密集区次要市场:窄屏隐藏引导线(标签也隐藏)· 只留标记点
          const lineCls = m.priority === 2 ? 'hidden md:block' : undefined
          return (
            <g key={m.symbol}>
              <line
                x1={m.x}
                y1={m.y}
                x2={m.lx}
                y2={m.ly}
                stroke={color}
                strokeWidth={0.7}
                opacity={0.45}
                className={lineCls}
              />
              <circle cx={m.x} cy={m.y} r={6.5} fill={color} opacity={0.16} />
              <circle cx={m.x} cy={m.y} r={3} fill={color} stroke="#fff" strokeWidth={0.9} />
            </g>
          )
        })}
      </svg>

      {/* HTML 标签层 · 不随 SVG 缩放、始终清晰 · 复用 text-up/down · 窄屏精简 */}
      <div className="pointer-events-none absolute inset-0">
        {markers.map((m) => {
          const up = m.changePct >= 0
          const leftPct = ((m.lx - VB_X) / VB_W) * 100
          const topPct = ((m.ly - VB_Y) / VB_H) * 100
          const tx = m.align === 'right' ? '-100%' : m.align === 'left' ? '0%' : '-50%'
          return (
            <div
              key={m.symbol}
              className={cn(
                'absolute flex items-center gap-1 whitespace-nowrap leading-none',
                m.priority === 2 && 'hidden md:flex',
              )}
              style={{ left: `${leftPct}%`, top: `${topPct}%`, transform: `translate(${tx}, -50%)` }}
            >
              <span className="text-[10px] text-muted-foreground md:text-xs">{m.short}</span>
              <span
                className={cn('font-mono text-[10px] font-semibold md:text-xs', up ? 'text-up' : 'text-down')}
              >
                {up ? '+' : ''}
                {m.changePct.toFixed(2)}%
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
