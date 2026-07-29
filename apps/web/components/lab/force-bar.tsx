'use client'

/**
 * 多空力量对比条(沙盘助手第一期)· 纯 CSS 双色占比条 · 零图表库依赖。
 *
 * 配色与全站涨跌语义一致:多 = 朱红 #DC143C(text-up/bg-up 体系)·
 * 空 = 墨绿 #0F6E5F。⛔ 不用淡灰蓝 #6482A0(缠论中枢专用 · CLAUDE.md 红线)。
 * 数据源:snapshot.account_long_short.value.latest(大户账户多空比 · 已有字段,
 * 旁路展示不进诊断链)· 比值非法 → 调用方拿 null 不渲染(优雅降级)。
 */

import { ratioToLongShortPct } from '@/lib/structure-viz'

interface ForceBarProps {
  /** 多空比值(long/short · 如 1.65) */
  ratio: number
  /** 来源标注(如「大户账户多空比 · latest」) */
  sourceLabel: string
  locale?: 'en' | 'zh'
}

export function ForceBar({ ratio, sourceLabel, locale = 'zh' }: ForceBarProps) {
  const pct = ratioToLongShortPct(ratio)
  if (pct === null) return null
  return (
    <div className="mt-3">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-mono font-medium text-up">
          {locale === 'en' ? 'Long' : '多'} {pct.longPct}%
        </span>
        <span className="text-[10px] text-muted-foreground/60">{sourceLabel}</span>
        <span className="font-mono font-medium text-down">
          {locale === 'en' ? 'Short' : '空'} {pct.shortPct}%
        </span>
      </div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full">
        <div className="bg-up" style={{ width: `${pct.longPct}%` }} />
        <div className="bg-down" style={{ width: `${pct.shortPct}%` }} />
      </div>
    </div>
  )
}
