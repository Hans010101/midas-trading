'use client'

/**
 * 详情页默认显示偏好(指标偏好系统 · 方案② · 刀1)· 设置页 section。
 *
 * 4 个指标图层开关(布林/缠论/MACD/做T)+ 默认周期(15m/1h/1d)· 初值读 display_prefs cookie,
 * 改动即写 cookie(纯前端 · 按浏览器保存 · 和涨跌色一致预期)。
 * ★刀1 只【存】偏好;详情页【刀2】才读它生效(本刀不碰详情页)。
 */

import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'
import {
  DEFAULT_DISPLAY_PREFS,
  type DisplayPrefs,
  readDisplayPrefs,
  writeDisplayPrefs,
} from '@/lib/display-prefs'

type IndicatorKey = keyof DisplayPrefs['indicators']

const INDICATORS: { key: IndicatorKey; label: string; note?: string }[] = [
  { key: 'boll', label: '布林带' },
  { key: 'chan', label: '缠论标注' },
  { key: 'macd', label: 'MACD' },
  { key: 'dott', label: '做T结构', note: '控制详情页是否显示做T结构模块' },
]

const PERIODS = ['15m', '1h', '1d']

export function DetailPrefsSection() {
  // 初始用系统默认(避免 SSR/首帧不一致)· 挂载后读 cookie 真实偏好
  const [prefs, setPrefs] = useState<DisplayPrefs>(DEFAULT_DISPLAY_PREFS)

  useEffect(() => {
    setPrefs(readDisplayPrefs())
  }, [])

  function toggleIndicator(key: IndicatorKey) {
    const next: DisplayPrefs = {
      ...prefs,
      indicators: { ...prefs.indicators, [key]: !prefs.indicators[key] },
    }
    writeDisplayPrefs(next) // 写 cookie
    setPrefs(next)
  }

  function choosePeriod(p: string) {
    if (p === prefs.period) return
    const next: DisplayPrefs = { ...prefs, period: p }
    writeDisplayPrefs(next)
    setPrefs(next)
  }

  return (
    <section className="mb-6 rounded-lg border border-paper bg-surface-card p-5">
      <h2 className="mb-1 font-serif text-lg font-bold text-foreground">详情页默认显示</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        设置打开币种详情页时,默认显示哪些图层、用哪个周期
      </p>

      {/* 指标图层开关 · 4 个 toggle */}
      <div className="mb-4 flex flex-col gap-2">
        {INDICATORS.map((it) => {
          const on = prefs.indicators[it.key]
          return (
            <div
              key={it.key}
              className="flex items-center justify-between gap-3 rounded-md border border-paper bg-background px-3 py-2.5"
            >
              <div className="flex flex-col">
                <span className="text-sm font-medium text-foreground">{it.label}</span>
                {it.note && (
                  <span className="text-[11px] text-muted-foreground/60">{it.note}</span>
                )}
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-label={it.label}
                onClick={() => toggleIndicator(it.key)}
                className={cn(
                  'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors',
                  on ? 'bg-midas-red' : 'bg-muted',
                )}
              >
                <span
                  className={cn(
                    'inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform',
                    on ? 'translate-x-5' : 'translate-x-0.5',
                  )}
                />
              </button>
            </div>
          )
        })}
      </div>

      {/* 默认周期 · 刀1 暴露 15m/1h/1d(5m/1w 刀2 验回源后再加)*/}
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">默认周期</span>
        <div className="flex overflow-hidden rounded-lg border border-paper">
          {PERIODS.map((p) => {
            const active = prefs.period === p
            return (
              <button
                key={p}
                type="button"
                onClick={() => choosePeriod(p)}
                aria-pressed={active}
                className={cn(
                  'px-4 py-1.5 text-sm font-medium transition-colors',
                  active
                    ? 'bg-midas-red text-white'
                    : 'bg-background text-foreground hover:bg-midas-red-glow/40',
                )}
              >
                {p}
              </button>
            )
          })}
        </div>
      </div>

      <p className="mt-4 text-[11px] text-muted-foreground/60">
        偏好按浏览器保存(非账号同步)· 详情页打开时按此默认显示(进页面后仍可临时调整)
      </p>
    </section>
  )
}
