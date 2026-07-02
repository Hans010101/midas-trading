'use client'

import { ThemeProvider as NextThemesProvider } from 'next-themes'
import type { ReactNode } from 'react'

/**
 * next-themes 包装(暗黑模式 P0 启用)。
 * ★attribute="class" → 挂 .dark 到 <html>,配 tailwind darkMode:'class' + globals.css .dark{}。
 * ★defaultTheme="system" + enableSystem → 默认跟随系统明暗(Hans 决策④)· 用户可手动覆盖。
 * ★与涨跌色 data-color-pref【正交】共存:theme 管 .dark class,color_pref 管 data 属性,互不干扰。
 * 偏好持久化走 next-themes 自带 localStorage + head 前置脚本(无闪烁·无后端·无迁移)。
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  )
}
