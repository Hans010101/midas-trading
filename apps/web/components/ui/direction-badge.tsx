import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 方向徽章 / 状态标签(0022 §3.4)· 收口存量 4 套手搓 pill。
 *
 * DirectionBadge:多/空、涨/跌 方向 —— 走 up/down 语义色(随涨跌偏好翻转)。
 *   long/up → up 色;short/down → down 色。可带杠杆后缀(perp 持仓)。
 *   (注:买/卖【下单动作】用品牌红填充/描边,属动作色而非方向色,走 Button,不在此。)
 *
 * StatusPill:状态标签(成交/拒单/强平/已激活…)· tone 语义化。
 */
type Direction = 'long' | 'short' | 'up' | 'down'

const DIR_LABEL: Record<Direction, string> = {
  long: '多',
  short: '空',
  up: '涨',
  down: '跌',
}

export function DirectionBadge({
  direction,
  label,
  leverage,
  className,
}: {
  direction: Direction
  /** 覆盖默认文案(默认 多/空/涨/跌) */
  label?: ReactNode
  /** 杠杆后缀(如 10 → "10x")· perp 持仓用 */
  leverage?: number
  className?: string
}) {
  const isUp = direction === 'long' || direction === 'up'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold text-white',
        isUp ? 'bg-up' : 'bg-down',
        className,
      )}
    >
      {label ?? DIR_LABEL[direction]}
      {leverage != null && ` ${leverage}x`}
    </span>
  )
}

type StatusTone = 'neutral' | 'success' | 'danger' | 'warn' | 'muted'

const STATUS_TONE: Record<StatusTone, string> = {
  neutral: 'bg-paper text-muted-foreground',
  success: 'bg-success/10 text-success',
  danger: 'bg-midas-red/10 text-midas-red',
  warn: 'bg-warn/10 text-warn',
  muted: 'text-muted-foreground',
}

export function StatusPill({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: StatusTone
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-1.5 py-0.5 text-[10px]',
        STATUS_TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
