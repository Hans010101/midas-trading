'use client'

/**
 * 主题外观开关(暗黑模式 P0)· 设置页 section。
 *
 * 三档:浅色 / 深色 / 跟随系统(默认)· 切换即时:next-themes setTheme → 挂 .dark 到 <html> 当场生效。
 * 持久化走 next-themes 自带 localStorage(无后端·无迁移)· head 前置脚本保证无闪烁。
 * ★与涨跌色偏好(color_pref)【正交】:主题管明暗、涨跌色管红绿翻转,两个独立设置互不影响。
 */

import { useTheme } from 'next-themes'
import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'

const OPTIONS: { value: string; label: string; note: string }[] = [
  { value: 'light', label: '浅色', note: '白天版' },
  { value: 'dark', label: '深色', note: '夜晚版' },
  { value: 'system', label: '跟随系统', note: '默认 · 跟 OS 明暗' },
]

export function ThemeSection() {
  const { theme, setTheme } = useTheme()
  // next-themes 在 SSR/首帧 theme 为 undefined → 挂载后再读真实值,避免 hydration 不一致
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const current = mounted ? (theme ?? 'system') : 'system'

  return (
    <section className="mb-6 rounded-lg border border-paper bg-surface-card p-5">
      <h2 className="mb-1 font-serif text-lg font-bold text-foreground">主题外观</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        明暗主题切换 · 即时生效 · ★只暗化背景 / 文字 / 容器,交易涨跌色语义不变
      </p>

      <div className="flex w-fit overflow-hidden rounded-lg border border-paper">
        {OPTIONS.map((o) => {
          const active = current === o.value
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => setTheme(o.value)}
              aria-pressed={active}
              className={cn(
                'flex min-w-[120px] flex-col items-start gap-0.5 px-4 py-3 text-left transition-colors',
                active
                  ? 'bg-midas-red text-white'
                  : 'bg-background text-foreground hover:bg-midas-red-glow/40',
              )}
            >
              <span className="text-sm font-medium">{o.label}</span>
              <span
                className={cn('text-[11px]', active ? 'text-white/75' : 'text-muted-foreground/70')}
              >
                {o.note}
              </span>
            </button>
          )
        })}
      </div>

      <p className="mt-3 text-[11px] text-muted-foreground/60">
        偏好按浏览器保存(非账号同步)· 与涨跌色偏好独立设置,互不影响
      </p>
    </section>
  )
}
