'use client'

/**
 * perp 持仓/订单共享小件(重组刀3 · 从 perp-positions-section 拆出,零逻辑改动)。
 * 三个子组件(active/closed/orders)共用 · 单一来源防漂移。
 */

import type { PerpAction } from '@/lib/api/perp'
import { cn } from '@/lib/utils'

export const ISOLATED_TIP = '逐仓:强平价只取决于开仓价与杠杆,与保证金金额无关'

export const ACTION_ZH: Record<PerpAction, string> = {
  open_long: '开多',
  open_short: '开空',
  close_long: '平多',
  close_short: '平空',
}

export const num = (s: string | null | undefined): number => (s == null ? 0 : Number(s) || 0)

export const fmtP = (s: string | null | undefined): string => {
  const n = num(s)
  return n >= 1 ? n.toLocaleString('en-US', { maximumFractionDigits: 2 }) : n.toFixed(4)
}

export const fmtU = (s: string | null | undefined): string =>
  num(s).toLocaleString('en-US', { maximumFractionDigits: 2 })

export function IsolatedTag() {
  return (
    <span
      title={ISOLATED_TIP}
      className="ml-1 cursor-help rounded bg-paper px-1 py-0.5 text-[9px] text-muted-foreground/80"
    >
      逐仓
    </span>
  )
}

export function SideBadge({ side, leverage }: { side: 'long' | 'short'; leverage: number }) {
  return (
    <span
      className={cn(
        'rounded px-1.5 py-0.5 text-[10px] font-bold text-white',
        side === 'long' ? 'bg-up' : 'bg-down',
      )}
    >
      {side === 'long' ? '多' : '空'} {leverage}x
    </span>
  )
}
