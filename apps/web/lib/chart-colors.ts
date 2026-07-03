'use client'

/**
 * 图表色板(暗黑模式 P1)· 让 canvas/SVG 图表(klinecharts / recharts)的配色跟页面主题对齐。
 *
 * ★核心:涨跌色直接读 globals.css 的 --color-up / --color-down(已 theme × color_pref 双感知:
 *   暗色下 = #F0495E 红 / #1FA588 绿;绿涨红跌偏好翻转;四组合都对)。图表用它 = 和 .dark token 一套色。
 * ★容器色(网格/坐标轴/文字/比值线)按 isDark 给两套 hex,避免亮色方案硬套暗底(Hans P1 痛点)。
 * ★浅色值 = 各图表原硬编码值,浅色零回归。
 */

import { useTheme } from 'next-themes'
import { useEffect, useState } from 'react'

export interface ChartColors {
  isDark: boolean
  up: string       // 涨(默认红)· --color-up · theme×color_pref 感知
  down: string     // 跌(默认绿)· --color-down
  grid: string     // 网格线
  axisText: string // 坐标轴刻度文字
  axisLine: string // 坐标轴 / 刻度线
  crosshair: string // 十字线(品牌红·两态都清晰)
  tooltipBg: string // tooltip 背景
  tooltipBorder: string
  neutral: string   // 比值线 / 中性描边(暗底要够亮)
}

const LIGHT: Omit<ChartColors, 'isDark' | 'up' | 'down'> = {
  grid: '#F0EEE8',
  axisText: '#94949C',
  axisLine: '#E5E2DA',
  crosshair: '#C8102E',
  tooltipBg: '#FCFCF9',
  tooltipBorder: '#F0EEE8',
  neutral: '#2A2A2A',
}

const DARK: Omit<ChartColors, 'isDark' | 'up' | 'down'> = {
  grid: '#242424',
  axisText: '#8A8A8A',
  axisLine: '#333333',
  crosshair: '#E0364C', // 暗底品牌红略提亮(和 .dark --midas-red 家族一致·色相不动)
  tooltipBg: '#1A1A1A',
  tooltipBorder: '#333333',
  neutral: '#B4B4B4', // 比值线暗底提亮(原 #2A2A2A 暗底不可见)
}

/**
 * 读当前主题的图表色板 · 主题(明暗)切换时自动重读(依赖 resolvedTheme)。
 * ★涨跌色每次从 CSS 变量取实时值(含 color_pref 翻转 + 暗色微调),不硬编码。
 */
export function useChartColors(): ChartColors {
  const { resolvedTheme } = useTheme()
  const [colors, setColors] = useState<ChartColors>({ isDark: false, up: '#DC143C', down: '#0F6E5F', ...LIGHT })

  useEffect(() => {
    const s = getComputedStyle(document.documentElement)
    const isDark = document.documentElement.classList.contains('dark')
    setColors({
      isDark,
      up: s.getPropertyValue('--color-up').trim() || '#DC143C',
      down: s.getPropertyValue('--color-down').trim() || '#0F6E5F',
      ...(isDark ? DARK : LIGHT),
    })
  }, [resolvedTheme])

  return colors
}
