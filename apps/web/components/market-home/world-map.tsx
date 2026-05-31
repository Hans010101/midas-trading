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

// 陆地点 = 浅红「灰粉」(与品牌红 #C8102E / 红涨 #DC143C 同色系 · 但极低饱和 + 高明度)。
// 设计意图:整图色觉与品牌统一,但底图是【背景】要退到后面 —— 饱和度仅约 22%、明度约 86%,
// 与饱和的「红涨」标记点(sat≈76% · light≈47%)在色度/明度上拉开大差,标记点稳稳浮在前景、绝不抢色。
const LAND = '#e7d3d6'

/**
 * 市场地理配置(静态 · 前端)· 阶段B 迭代扩成 10 个(都有明确地理归属)。
 * (lx, ly) = 标签锚点(viewBox 单位)· 从标记点拉引导线到此 · 密集簇(欧洲 3 / 东亚 4)用 callout 竖排防重叠。
 * priority 1 = 地理孤立的主要市场(窄屏也显示标签);2 = 密集簇次要(★ 窄屏只留标记点、隐藏标签防糊)。
 * ★ 窄屏策略(市场变多后):所有标记点全留(颜色仍显地理涨跌),标签只留 4 个地理分散的 priority 1。
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

// 精选扩充后 16 个上图(其余新增指数 STOXX50/罗素2000/沪深300/深证 无独立地理 → 仅卡片)。
// 窄屏 priority 1 = 6 个跨大洲分散的(标普/富时/印度/日经/巴西/澳),窄屏只显示这 6 标签、其余只留点。
const MARKET_GEO: readonly MarketGeo[] = [
  // 美洲
  { symbol: '^GSPC', short: '标普', lng: -74, lat: 40.7, lx: 246, ly: 200, align: 'center', priority: 1 },
  { symbol: '^GSPTSE', short: '加拿大', lng: -79.4, lat: 43.6, lx: 206, ly: 92, align: 'right', priority: 2 },
  { symbol: '^BVSP', short: '巴西', lng: -46.6, lat: -23.5, lx: 300, ly: 328, align: 'right', priority: 1 },
  // 欧洲簇(伦敦/巴黎/法兰克福/苏黎世很挤)· 伦敦+巴黎向左、DAX+瑞士向右 分两摞
  { symbol: '^FTSE', short: '富时', lng: -0.1, lat: 51.5, lx: 436, ly: 48, align: 'right', priority: 1 },
  { symbol: '^FCHI', short: '法CAC', lng: 2.35, lat: 48.86, lx: 436, ly: 74, align: 'right', priority: 2 },
  { symbol: '^GDAXI', short: 'DAX', lng: 8.7, lat: 50.1, lx: 594, ly: 50, align: 'left', priority: 2 },
  { symbol: '^SSMI', short: '瑞士', lng: 8.5, lat: 47.4, lx: 594, ly: 76, align: 'left', priority: 2 },
  // 南亚(孟买 · 单独标向左)
  { symbol: '^NSEI', short: '印度', lng: 72.8, lat: 19.0, lx: 632, ly: 208, align: 'right', priority: 1 },
  // 东亚 + 东南亚(东京/首尔/上海/台湾/香港/新加坡/雅加达很挤)· 统一向右(太平洋)callout 单列竖排。
  // ★ ly 严格按【纬度从北到南】排(首尔→东京→上海→台湾→香港→新STI→印尼),
  //   与标记点 y 同序 → 引导线单调扇出、互不交叉(防原 日经/韩 标签错位交叉)。每条 26px 错落、清晰不重叠。
  { symbol: '^KS11', short: '韩KOSPI', lng: 127, lat: 37.57, lx: 954, ly: 104, align: 'right', priority: 2 },
  { symbol: '^N225', short: '日经', lng: 139.7, lat: 35.7, lx: 954, ly: 130, align: 'right', priority: 1 },
  { symbol: '000001.SS', short: '上证', lng: 121.5, lat: 31.2, lx: 954, ly: 156, align: 'right', priority: 2 },
  { symbol: '^TWII', short: '台湾', lng: 121.5, lat: 25.0, lx: 954, ly: 182, align: 'right', priority: 2 },
  { symbol: '^HSI', short: '恒生', lng: 114.2, lat: 22.3, lx: 954, ly: 208, align: 'right', priority: 2 },
  { symbol: '^STI', short: '新STI', lng: 103.8, lat: 1.35, lx: 954, ly: 234, align: 'right', priority: 2 },
  { symbol: '^JKSE', short: '印尼', lng: 106.8, lat: -6.2, lx: 954, ly: 260, align: 'right', priority: 2 },
  // 大洋洲(悉尼 · 右下、孤立)
  { symbol: '^AXJO', short: '澳ASX', lng: 151.2, lat: -33.87, lx: 860, ly: 362, align: 'right', priority: 1 },
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
