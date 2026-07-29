'use client'

import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { useChartColors } from '@/lib/chart-colors'

/**
 * 行业板块热力图(共享组件)· A股 / 美股 / 港股 三市场首页复用。
 *
 * 响应式色块网格(手机 2 列 → 桌面 6 列)· 每块:板块名 + 涨跌%(JetBrains Mono 大字)+ 家数。
 * 底色 = 涨 var(--color-up #DC143C)/ 跌 var(--color-down #0F6E5F)· 深浅按 |涨跌%| 映射透明度
 * (浅色洗 · 深字保持可读 · 契合白底暖米白基调)· 用 color-mix 走 CSS 变量 → 自动随「红涨绿跌/绿涨红跌」偏好翻转。
 * 降序排(强左上 → 弱右下)· hover(title)提示领涨/家数/成交额 · 色块不可点。
 *
 * 红线:只读行情展示 · 色块不可点(暂无板块详情页)· 不碰下单/撮合。
 *
 * ★暗黑 P3:底色 color-mix 走 --color-up/down(暗色 #F0495E/#1FA588 · color_pref 翻转自动),
 *   ★但透明度映射(depthPct)按明暗分档:同一 transparent 混合叠在暗卡片上偏弱,弱板块色信号
 *   会糊进暗底 → 暗底抬高下限与斜率,保证强弱色阶清晰(色相不动·只调透明度/明度)。浅色映射
 *   字节不变(零回归)。isDark 走 useChartColors(P1 hook·MutationObserver 切主题即时跟随)。
 */

export interface HeatmapSector {
  name: string
  change_pct: number
  stock_count: number
  total_amount: number
  /** A股 / 港股有领涨股;美股聚合无 → 可选(hover 提示按有无渲染)。 */
  leader_name?: string
  leader_change_pct?: number
}

interface SectorHeatmapProps {
  sectors: HeatmapSector[]
  /** 成交额格式化(各市场币种不同:A股/港股 亿/万 · 美股 $B/$M)。 */
  fmtAmount: (n: number) => string
  /** 色块上限(A股 ~49 板块 → cap 24 清爽;美股/港股 ~12 不传即全显)。 */
  max?: number
}

function fmtPct(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

// |涨跌%| → color-mix 透明度百分比。
// 浅色洗(原映射·零回归):0% 板块 ≈ 10% 洗,≥3% 板块封顶 70%(深字仍可读)。
// 暗底(★P3):同 transparent 混合在暗卡片上偏弱 → 抬高下限 22% + 斜率 22 + 封顶 88,
//   弱板块也有可见红/绿信号、强弱色阶清晰(色相不动·只调透明度/明度)。
function depthPct(changePct: number, isDark: boolean): number {
  if (isDark) {
    const a = 22 + Math.abs(changePct) * 22
    return Math.min(88, Math.max(22, a))
  }
  const a = 10 + Math.abs(changePct) * 20
  return Math.min(70, Math.max(10, a))
}

function tileTip(
  s: HeatmapSector,
  fmtAmount: (n: number) => string,
  locale: 'en' | 'zh',
): string {
  const base = locale === 'en'
    ? `${s.name} · Change ${fmtPct(s.change_pct)} · ${s.stock_count} stocks · Turnover ${fmtAmount(s.total_amount)}`
    : `${s.name} · 涨跌 ${fmtPct(s.change_pct)} · 家数 ${s.stock_count} · 成交额 ${fmtAmount(s.total_amount)}`
  if (s.leader_name) {
    return locale === 'en'
      ? `${base} · Leader ${s.leader_name} ${fmtPct(s.leader_change_pct ?? 0)}`
      : `${base} · 领涨 ${s.leader_name} ${fmtPct(s.leader_change_pct ?? 0)}`
  }
  return base
}

export function SectorHeatmap({ sectors, fmtAmount, max }: SectorHeatmapProps) {
  const { locale } = useRuntimeLocale()
  const { isDark } = useChartColors() // ★P3:暗底透明度映射分档 · 切主题即时跟随
  // 降序排(强左上 → 弱右下)· 后端通常已 DESC,这里防御性再排一次
  const sorted = [...sectors].sort((a, b) => b.change_pct - a.change_pct)
  const shown = max ? sorted.slice(0, max) : sorted

  return (
    <div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {shown.map((s) => {
          const varName = s.change_pct >= 0 ? '--color-up' : '--color-down'
          const bg = `color-mix(in srgb, var(${varName}) ${depthPct(s.change_pct, isDark)}%, transparent)`
          return (
            <div
              key={s.name}
              title={tileTip(s, fmtAmount, locale)}
              style={{ backgroundColor: bg }}
              className="rounded-md border border-border/50 px-3 py-2.5 transition-colors"
            >
              <div className="truncate text-sm font-medium text-foreground">{s.name}</div>
              <div className="mt-1 font-mono text-lg font-bold text-foreground">
                {fmtPct(s.change_pct)}
              </div>
              <div className="mt-0.5 text-[11px] text-muted-foreground/70">
                {locale === 'en' ? `${s.stock_count} stocks` : `${s.stock_count} 只`}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
