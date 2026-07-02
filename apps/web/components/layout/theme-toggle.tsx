'use client'

/**
 * 顶栏主题快捷切换(暗黑模式 P0)· 浅↔深 一键切。
 * 用 resolvedTheme 判当前实际明暗(解析 system);点击设显式 light/dark(next-themes localStorage 持久)。
 * ★挂载前渲染等宽占位,避免 SSR/首帧 hydration 不一致与布局跳动。
 */

import { Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'
import { useEffect, useState } from 'react'

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  if (!mounted) {
    return <div className="h-8 w-8 shrink-0" aria-hidden />
  }
  const isDark = resolvedTheme === 'dark'
  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={isDark ? '切换到浅色主题' : '切换到深色主题'}
      title={isDark ? '切换到浅色' : '切换到深色'}
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-paper bg-surface-subtle/40 text-muted-foreground transition-colors hover:border-midas-red/30 hover:text-foreground"
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  )
}
