'use client'

/**
 * 世界地图视觉模块(ADR 0035 阶段 B · 纯前端视觉增强)。
 *
 * 读阶段 A 同一份 /overview/global 数据(主要股指),不新增后端、不碰数据层。
 * 渲染:点阵风格世界地图(Natural Earth 110m 采样 · 见 world-dots.ts)+ 各市场标记点 + 标签。
 *
 * 标签布局(富途简洁风 · 产品负责人定调):★ 标签【就近贴点放】—— 点的上/下/左/右哪边空放哪边,
 *   默认【不画引导线】。亚太就近分散(韩在点上 / 日经在点右 / 上证·恒生·新STI在点左 / 台湾·印尼在点右),
 *   不再拉到右侧太平洋一列。只有真正挤到一起的极少数(欧洲 4:伦敦/巴黎/法兰克福/苏黎世)才用【短】线
 *   稍微错开;绝不用长线横跨大陆。
 * 配色铁律(★ 与阶段 A 一致):涨跌严格复用 `--color-up` / `--color-down`(默认红涨绿跌),
 *   随用户偏好与卡片同步翻转。陆地点用中性冷灰(非暖色)。
 * 响应式:HTML 标签层叠在 SVG 上(不随 viewBox 缩放、始终清晰);窄屏隐藏密集区次要标签(priority 2),
 *   只留标记点 + 地理分散的 priority 1 标签,避免糊成一团。
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

// 陆地点 = 浅红「灰粉」(与品牌红 #C8102E / 红涨 #DC143C 同色系 · 但极低饱和 + 高明度),退到背景。
const LAND = '#e7d3d6'

/**
 * 市场地理配置(静态 · 前端)。
 * (lng, lat) = 标记点地理位置(投影到 viewBox · 不动);(dx, dy) = 标签相对标记点的【就近偏移】(viewBox 单位 · 选周围空白侧)。
 * align = 文字锚点(right=贴点左侧 / left=贴点右侧 / center=贴点上下);line = 是否画短引导线(默认 false · 仅欧洲极挤 4 个 true)。
 * priority 1 = 地理孤立的主要市场(窄屏也显示标签);2 = 密集簇次要(★ 窄屏只留标记点)。
 */
type MarketGeo = {
  symbol: string
  short: string
  lng: number
  lat: number
  dx: number
  dy: number
  align: 'left' | 'right' | 'center'
  line?: boolean
  priority: 1 | 2
}

// ★ 富途简洁风:标签贴点就近放、默认无引导线。仅欧洲 4 个(伦敦/巴黎/法兰克福/苏黎世)极挤 → 短线错开。
const NEAR = 9 // 左右贴点的水平偏移(viewBox 单位 · 刚好出标记点光圈、贴而不压)
const MARKET_GEO: readonly MarketGeo[] = [
  // 美洲(各自孤立 · 贴点放)
  { symbol: '^GSPC', short: '标普', lng: -74, lat: 40.7, dx: -NEAR, dy: 0, align: 'right', priority: 1 },
  { symbol: '^GSPTSE', short: '加拿大', lng: -79.4, lat: 43.6, dx: 0, dy: -11, align: 'center', priority: 2 },
  { symbol: '^BVSP', short: '巴西', lng: -46.6, lat: -23.5, dx: -NEAR, dy: 0, align: 'right', priority: 1 },
  // 欧洲簇(伦敦/巴黎/法兰克福/苏黎世极挤)· ★ 全图唯一用短线:伦敦+巴黎向左、DAX+瑞士向右,短线稍错开
  { symbol: '^FTSE', short: '富时', lng: -0.1, lat: 51.5, dx: -30, dy: -7, align: 'right', line: true, priority: 1 },
  { symbol: '^FCHI', short: '法CAC', lng: 2.35, lat: 48.86, dx: -37, dy: 8, align: 'right', line: true, priority: 2 },
  { symbol: '^GDAXI', short: 'DAX', lng: 8.7, lat: 50.1, dx: 34, dy: -6, align: 'left', line: true, priority: 2 },
  { symbol: '^SSMI', short: '瑞士', lng: 8.5, lat: 47.4, dx: 34, dy: 9, align: 'left', line: true, priority: 2 },
  // 南亚(孟买 · 贴点向左 · 不再写到非洲)
  { symbol: '^NSEI', short: '印度', lng: 72.8, lat: 19.0, dx: -NEAR, dy: 0, align: 'right', priority: 1 },
  // 东亚 / 东南亚:就近分散(不再拉成右侧一列)· 无引导线
  { symbol: '^N225', short: '日经', lng: 139.7, lat: 35.7, dx: NEAR, dy: 0, align: 'left', priority: 1 },
  { symbol: '^KS11', short: '韩KOSPI', lng: 127, lat: 37.57, dx: 0, dy: -11, align: 'center', priority: 2 },
  { symbol: '000001.SS', short: '上证', lng: 121.5, lat: 31.2, dx: -NEAR, dy: 0, align: 'right', priority: 2 },
  { symbol: '^TWII', short: '台湾', lng: 121.5, lat: 25.0, dx: NEAR, dy: 0, align: 'left', priority: 2 },
  { symbol: '^HSI', short: '恒生', lng: 114.2, lat: 22.3, dx: -NEAR, dy: 0, align: 'right', priority: 2 },
  { symbol: '^STI', short: '新STI', lng: 103.8, lat: 1.35, dx: -NEAR, dy: 0, align: 'right', priority: 2 },
  { symbol: '^JKSE', short: '印尼', lng: 106.8, lat: -6.2, dx: NEAR, dy: 0, align: 'left', priority: 2 },
  // 大洋洲(悉尼 · 贴点向右)
  { symbol: '^AXJO', short: '澳ASX', lng: 151.2, lat: -33.87, dx: NEAR, dy: 0, align: 'left', priority: 1 },
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
    <div className="relative w-full">
      <svg
        viewBox={`${VB_X} ${VB_Y} ${VB_W} ${VB_H}`}
        className="block h-auto w-full"
        role="img"
        aria-label="全球主要股指地理分布"
      >
        {/* 陆地点阵(浅红灰粉 · 退到背景) */}
        <g fill={LAND}>
          {WORLD_DOTS.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={1.5} />
          ))}
        </g>
        {/* 短引导线(★ 仅欧洲极挤的 4 个)+ 标记点(红涨绿跌 · 复用 --color-up/down) */}
        {markers.map((m) => {
          const color = m.changePct >= 0 ? 'var(--color-up)' : 'var(--color-down)'
          // 密集区次要市场:窄屏隐藏引导线(标签也隐藏)· 只留标记点
          const lineCls = m.priority === 2 ? 'hidden md:block' : undefined
          return (
            <g key={m.symbol}>
              {m.line && (
                <line
                  x1={m.x}
                  y1={m.y}
                  x2={m.x + m.dx}
                  y2={m.y + m.dy}
                  stroke={color}
                  strokeWidth={0.7}
                  opacity={0.4}
                  className={lineCls}
                />
              )}
              <circle cx={m.x} cy={m.y} r={6.5} fill={color} opacity={0.16} />
              <circle cx={m.x} cy={m.y} r={3} fill={color} stroke="#fff" strokeWidth={0.9} />
            </g>
          )
        })}
      </svg>

      {/* HTML 标签层 · 贴点就近放 · 不随 SVG 缩放、始终清晰 · 窄屏精简 */}
      <div className="pointer-events-none absolute inset-0">
        {markers.map((m) => {
          const up = m.changePct >= 0
          // 标签锚点 = 标记点 + 就近偏移(dx, dy)
          const leftPct = ((m.x + m.dx - VB_X) / VB_W) * 100
          const topPct = ((m.y + m.dy - VB_Y) / VB_H) * 100
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
