'use client'

/**
 * 图表色板(暗黑模式 P1)· 让 canvas/SVG 图表(klinecharts / recharts)的配色跟页面主题对齐。
 *
 * ★核心:涨跌色直接读 globals.css 的 --color-up / --color-down(已 theme × color_pref 双感知:
 *   暗色下 = #F0495E 红 / #1FA588 绿;绿涨红跌偏好翻转;四组合都对)。图表用它 = 和 .dark token 一套色。
 * ★容器色(网格/坐标轴/文字/比值线)按 isDark 给两套 hex,避免亮色方案硬套暗底(Hans P1 痛点)。
 * ★浅色值 = 各图表原硬编码值,浅色零回归。
 */

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

/** 从 <html> 实时读色板:isDark 看 .dark class · 涨跌色取 CSS 变量(含 color_pref 翻转 + 暗色微调)。 */
function readChartColors(): ChartColors {
  const s = getComputedStyle(document.documentElement)
  const isDark = document.documentElement.classList.contains('dark')
  return {
    isDark,
    up: s.getPropertyValue('--color-up').trim() || '#DC143C',
    down: s.getPropertyValue('--color-down').trim() || '#0F6E5F',
    ...(isDark ? DARK : LIGHT),
  }
}

/**
 * 读当前主题的图表色板 · 明暗 / 涨跌偏好切换时【立即】重读,无需刷新页面。
 *
 * ★为什么用 MutationObserver 而不是依赖 next-themes 的 resolvedTheme(P1 收尾修 bug):
 *   - 切主题时消费组件的 effect(子)在 next-themes provider 的 applyTheme effect(父)【之前】跑
 *     (React 提交阶段子 effect 先于父 effect)→ 依赖 resolvedTheme 重读会读到【旧 .dark class】,
 *     图表停在旧配色、必须刷新才对(Hans 真机 P1 反馈的 bug)。
 *   - color_pref 切换根本不改 resolvedTheme → 依赖它的 hook 完全不重读,同样 stale。
 *   MutationObserver 监听 <html> 的 class(明暗)+ data-color-pref(涨跌偏好),在 DOM 属性
 *   【真正改变后】才回调重读 → 绕开 effect 执行顺序竞态,两种切换都当场跟随。
 */
export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>({ isDark: false, up: '#DC143C', down: '#0F6E5F', ...LIGHT })

  useEffect(() => {
    // 挂载即读真实值(no-flash 前置脚本已把 class / data-color-pref 落到 <html>,首读正确)
    setColors(readChartColors())

    const observer = new MutationObserver(() => {
      setColors((prev) => {
        const next = readChartColors()
        // 无实质变化(isDark + 涨跌色三者相同 → 容器色也相同)复用旧引用,避免图表无谓重绘
        if (next.isDark === prev.isDark && next.up === prev.up && next.down === prev.down) {
          return prev
        }
        return next
      })
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'data-color-pref'],
    })
    return () => observer.disconnect()
  }, [])

  return colors
}
