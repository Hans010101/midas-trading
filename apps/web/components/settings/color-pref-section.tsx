'use client'

/**
 * 涨跌色偏好开关(0023 阶段③ · 3.5 · 决策⑧)· 设置页 section。
 *
 * 一个二选一开关:红涨绿跌(默认)⇄ 绿涨红跌。
 * 切换即时:写 cookie + 设 <html data-color-pref> → 全产品(A股/美股/加密)涨跌色当场翻转,无需刷新。
 * 持久化为 cookie(纯前端,见 lib/color-pref.ts)· 刷新后保持。
 */

import { useEffect, useState } from 'react'

import {
  type ColorPref,
  DEFAULT_COLOR_PREF,
  applyColorPref,
  readColorPref,
} from '@/lib/color-pref'
import { cn } from '@/lib/utils'

const OPTIONS: { value: ColorPref; label: string; note: string }[] = [
  { value: 'red-up', label: '红涨绿跌', note: '默认 · A股传统' },
  { value: 'green-up', label: '绿涨红跌', note: '欧美 / 港股习惯' },
]

export function ColorPrefSection() {
  // 初始用默认避免 SSR/首帧不一致;挂载后读真实偏好(<html data-color-pref> 或 cookie)
  const [pref, setPref] = useState<ColorPref>(DEFAULT_COLOR_PREF)

  useEffect(() => {
    setPref(readColorPref())
  }, [])

  function choose(next: ColorPref) {
    if (next === pref) return
    applyColorPref(next) // 写 cookie + 即时翻转 <html data-color-pref>
    setPref(next)
  }

  return (
    <section className="mb-6 rounded-lg border border-paper bg-surface-card p-5">
      <h2 className="mb-1 font-serif text-lg font-bold text-foreground">涨跌色偏好</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        选择涨跌的颜色习惯 · 即时生效于全站 A股 / 美股 / 加密的行情、榜单、K 线
      </p>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
        {/* 二选一开关 */}
        <div className="flex overflow-hidden rounded-lg border border-paper">
          {OPTIONS.map((o) => {
            const active = pref === o.value
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => choose(o.value)}
                aria-pressed={active}
                className={cn(
                  'flex min-w-[140px] flex-col items-start gap-0.5 px-4 py-3 text-left transition-colors',
                  active
                    ? 'bg-midas-red text-white'
                    : 'bg-background text-foreground hover:bg-midas-red-glow/40',
                )}
              >
                <span className="text-sm font-medium">{o.label}</span>
                <span className={cn('text-[11px]', active ? 'text-white/75' : 'text-muted-foreground/70')}>
                  {o.note}
                </span>
              </button>
            )
          })}
        </div>

        {/* 实时预览:涨 / 跌 各一行,用当前偏好的语义色 */}
        <div className="flex flex-1 items-center justify-around rounded-lg border border-dashed border-paper bg-background px-4 py-3 font-mono text-sm">
          <div className="text-center">
            <div className="text-[10px] text-muted-foreground/70">涨</div>
            <div className="font-bold text-up">+1.23%</div>
          </div>
          <div className="text-center">
            <div className="text-[10px] text-muted-foreground/70">跌</div>
            <div className="font-bold text-down">−1.23%</div>
          </div>
        </div>
      </div>

      <p className="mt-3 text-[11px] text-muted-foreground/60">
        偏好按浏览器保存(非账号同步)· 中枢淡灰蓝等其它配色不受影响
      </p>
    </section>
  )
}
