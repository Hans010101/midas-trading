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
import { type FactorHeadline, type Tone, isDivergentFinding, stateTone } from '@/lib/structure-viz'
import { cn } from '@/lib/utils'

// 状态胶囊 / 数值 tone → 色(朱红多 / 墨绿空 / 中性灰 · 全站涨跌语义)
// stateTone 移至 lib/structure-viz(刀D-B:headline/sparkline 档位收敛与胶囊同源)
const TONE_TEXT: Record<Tone, string> = {
  bull: 'text-up', bear: 'text-down', neutral: 'text-muted-foreground',
}

interface FactorCardProps {
  /** null = LLM 未对该因子输出判定(批1 修复刀)→ 降级卡:数值+图 · 判定如实留白不伪造 */
  finding: FactorFinding | null
  label: string
  /** 数据窗口胶囊(有 finding 用其 window,否则用 snapshot 因子的 window) */
  window: string
  series: SparkPoint[] | null
  /** 关键数值(snapshot 结构化字段 · factorHeadline 算好传入)· null 不显示 */
  headline?: FactorHeadline | null
  /** sparkline 语义线色 / 基准线(sparklineSpec 算好传入) */
  sparkStroke?: string
  sparkBaseline?: number
  locale?: 'en' | 'zh'
}

export function FactorCard({
  finding,
  label,
  window: windowLabel,
  series,
  headline = null,
  sparkStroke,
  sparkBaseline,
  locale = 'zh',
}: FactorCardProps) {
  const divergent = finding != null && isDivergentFinding(finding)
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
              {locale === 'en' ? 'Divergence / extreme' : '背离/极端'}
            </span>
          )}
        </div>
        <span className="rounded bg-surface-subtle px-1.5 py-0.5 font-mono text-[10px] text-faint">
          {windowLabel}
        </span>
      </div>
      {/* 状态色块胶囊(仅 LLM 有判定时)+ mono 关键数值(snapshot 结构化取数) */}
      <div className="mt-1.5 flex items-center gap-2">
        {finding && (
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-xs font-medium',
              stateTone(finding.state) === 'bull' && 'bg-up/10 text-up',
              stateTone(finding.state) === 'bear' && 'bg-down/10 text-down',
              stateTone(finding.state) === 'neutral' && 'bg-surface-subtle text-muted-foreground',
            )}
          >
            {finding.state}
          </span>
        )}
        {headline && (
          <span className={cn('font-mono text-lg font-bold tabular-nums', TONE_TEXT[headline.tone])}>
            {headline.text}
          </span>
        )}
      </div>
      {series !== null && <Sparkline data={series} stroke={sparkStroke} baseline={sparkBaseline} />}
      {finding && (
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{finding.detail}</p>
      )}
    </div>
  )
}
