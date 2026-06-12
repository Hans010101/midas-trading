'use client'

/**
 * 因子状态卡(沙盘助手第一期)· 从 assistant/page.tsx 抽出 + 可视化升级。
 *
 * 每卡:因子名 + window 胶囊 + 状态判定 + ★ sparkline(新)+ detail 文字。
 * ★ 背离高亮:LLM 在 state/detail 点名「背离/极端」→ border-gold + 金底 badge
 *   (照现有 gold badge 范式 · 帝王金警示语义)。
 * 纯展示组件(无 hook · series 由父层固定 hooks 算好传入,符合 React 规则)。
 * series=null(sentiment 无时序 hook / 数据未到)→ 图区不渲染,文字照常(优雅降级)。
 */

import { Sparkline, type SparkPoint } from '@/components/lab/sparkline'
import type { FactorFinding } from '@/lib/api/structure'
import { type FactorHeadline, type Tone, isDivergentFinding } from '@/lib/structure-viz'
import { cn } from '@/lib/utils'

// 状态胶囊 / 数值 tone → 色(朱红多 / 墨绿空 / 中性灰 · 全站涨跌语义)
const TONE_TEXT: Record<Tone, string> = {
  bull: 'text-up', bear: 'text-down', neutral: 'text-muted-foreground',
}

function stateTone(state: string): Tone {
  if (/多/.test(state)) return 'bull'
  if (/空/.test(state)) return 'bear'
  return 'neutral'
}

interface FactorCardProps {
  finding: FactorFinding
  label: string
  series: SparkPoint[] | null
  /** 关键数值(snapshot 结构化字段 · factorHeadline 算好传入)· null 不显示 */
  headline?: FactorHeadline | null
  /** sparkline 语义线色 / 基准线(sparklineSpec 算好传入) */
  sparkStroke?: string
  sparkBaseline?: number
}

export function FactorCard({
  finding, label, series, headline = null, sparkStroke, sparkBaseline,
}: FactorCardProps) {
  const divergent = isDivergentFinding(finding)
  const tone = stateTone(finding.state)
  return (
    <div
      className={cn(
        'rounded-lg border bg-cream p-3 shadow-sm',
        divergent ? 'border-gold/60' : 'border-paper',
      )}
    >
      <div className="flex items-baseline justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">{label}</span>
          {divergent && (
            <span className="rounded bg-gold/15 px-1.5 py-0.5 text-[10px] text-gold">
              背离/极端
            </span>
          )}
        </div>
        <span className="rounded bg-surface-subtle px-1.5 py-0.5 font-mono text-[10px] text-faint">
          {finding.window}
        </span>
      </div>
      {/* 状态色块胶囊 + mono 关键数值(snapshot 结构化取数 · ⛔ 不解析 LLM 文字) */}
      <div className="mt-1.5 flex items-center gap-2">
        <span
          className={cn(
            'rounded px-1.5 py-0.5 text-xs font-medium',
            tone === 'bull' && 'bg-up/10 text-up',
            tone === 'bear' && 'bg-down/10 text-down',
            tone === 'neutral' && 'bg-surface-subtle text-muted-foreground',
          )}
        >
          {finding.state}
        </span>
        {headline && (
          <span className={cn('font-mono text-lg font-bold tabular-nums', TONE_TEXT[headline.tone])}>
            {headline.text}
          </span>
        )}
      </div>
      {series !== null && <Sparkline data={series} stroke={sparkStroke} baseline={sparkBaseline} />}
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{finding.detail}</p>
    </div>
  )
}
