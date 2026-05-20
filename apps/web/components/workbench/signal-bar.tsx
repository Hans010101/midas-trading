'use client'

/**
 * 顶部信号条 · 0012 ADR M1 二波 Checkpoint Z(替换 M0 占位)。
 *
 * 横向布局(从左到右):
 *   - 标签:「AI 信号」
 *   - 信号强度(综合评分大字 + 5 档标签)
 *   - 趋势方向:近期笔方向 + 中枢数量
 *   - mock 标记(若 llm_mode='mock')
 *   - DisclaimerStrip(compact)
 *
 * 数据来源:复用 useAiDecision · 跟右栏 AI 决策卡共享 cache · 不发额外请求。
 */

import { useMemo } from 'react'

import { DisclaimerStrip } from '@/components/workbench/disclaimer-strip'
import { useAiDecision } from '@/hooks/use-ai-decision'
import type { CompositeLabel, DecisionCard } from '@/lib/api/ai-decision'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'


export function SignalBar() {
  const symbol = useWorkbenchStore((s) => s.symbol)
  const market = useWorkbenchStore((s) => s.market)
  const period = useWorkbenchStore((s) => s.period)

  const query = useAiDecision({ symbol, market, period })

  return (
    <div className="flex h-10 shrink-0 items-center gap-4 border-b border-paper bg-cream/50 px-4">
      <span className="font-serif text-xs font-bold text-foreground">
        AI 信号
      </span>
      <div className="flex flex-1 items-center gap-4">
        {query.status === 'pending' && (
          <span className="text-xs text-muted-foreground/60">分析中...</span>
        )}
        {query.status === 'error' && (
          <span className="text-xs text-muted-foreground/60">暂无信号</span>
        )}
        {query.status === 'success' && <SignalBarBody card={query.data} />}
      </div>
      <DisclaimerStrip compact />
    </div>
  )
}


function SignalBarBody({ card }: { card: DecisionCard }) {
  const labelColor = useMemo(
    () => composeLabelColor(card.composite_label), [card.composite_label],
  )
  const recentSignals = card.chan_signals.slice(-1)

  return (
    <>
      {/* 综合评分 */}
      <div className="flex items-center gap-2">
        <span className={cn('font-mono text-base font-bold tabular-nums', labelColor)}>
          {card.composite_score > 0 ? '+' : ''}{card.composite_score}
        </span>
        <span className={cn('text-xs font-medium', labelColor)}>
          {card.composite_label}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground/60">
          置信度 {(card.composite_confidence * 100).toFixed(0)}%
        </span>
      </div>

      {/* 最近一个买卖点 */}
      {recentSignals.length > 0 && (
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-muted-foreground/60">最近</span>
          {recentSignals.map((s) => {
            const isBuy = s.kind.startsWith('B')
            return (
              <span
                key={s.ts}
                className={cn(
                  'inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px] font-bold',
                  isBuy ? 'bg-bull/10 text-bull' : 'bg-bear/10 text-bear',
                )}
                title={s.description}
              >
                {s.kind} @ {s.price.toFixed(2)}
              </span>
            )
          })}
        </div>
      )}

      {/* mock 标记 */}
      {card.llm_mode === 'mock' && (
        <span className="rounded bg-gold/10 px-1.5 py-0.5 font-mono text-[10px] text-gold">
          mock
        </span>
      )}
    </>
  )
}


function composeLabelColor(label: CompositeLabel): string {
  switch (label) {
    case '强多':
    case '弱多':
      return 'text-bull'
    case '强空':
    case '弱空':
      return 'text-bear'
    default:
      return 'text-muted-foreground'
  }
}
