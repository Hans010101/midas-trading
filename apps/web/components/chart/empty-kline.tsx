'use client'

/**
 * 空数据态占位卡 · 实现 docs/decisions/0005-empty-data-state.md。
 *
 * 三态文案矩阵:
 *   empty       回填中(默认)→ 一键切换到日 K
 *   not-found   标的不存在    → 返回自选股(M0 不实装回调)
 *   unavailable 上游不可达    → 重试
 */

import { Button } from '@/components/ui/button'

export type EmptyKlineReason = 'empty' | 'not-found' | 'unavailable'

interface EmptyKlineProps {
  reason: EmptyKlineReason
  onSwitchToDaily?: () => void
  onRetry?: () => void
}

const COPY: Record<EmptyKlineReason, { title: string; subtitle: string }> = {
  empty: {
    title: '该周期数据回填中',
    subtitle: '请切换到日 K 查看,小时/分钟 K 数据正在跟进',
  },
  'not-found': {
    title: '标的不存在或已下架',
    subtitle: '请确认代码或换一只标的',
  },
  unavailable: {
    title: '数据源临时不可达',
    subtitle: '上游 API 短暂抖动,稍候再试',
  },
}

export function EmptyKline({ reason, onSwitchToDaily, onRetry }: EmptyKlineProps) {
  const { title, subtitle } = COPY[reason]
  return (
    <div className="flex h-full w-full min-h-[400px] items-center justify-center bg-cream rounded-lg border border-paper">
      <div className="flex flex-col items-center gap-4 px-8 py-12 text-center">
        <div aria-hidden className="text-6xl text-ink-faint">
          📊
        </div>
        <h2 className="font-serif text-2xl font-bold text-foreground">{title}</h2>
        <p className="font-sans text-sm text-muted-foreground max-w-md">{subtitle}</p>
        {reason === 'empty' && onSwitchToDaily && (
          <Button size="sm" onClick={onSwitchToDaily}>
            切到日 K
          </Button>
        )}
        {reason === 'unavailable' && onRetry && (
          <Button size="sm" onClick={onRetry}>
            重试
          </Button>
        )}
      </div>
    </div>
  )
}
