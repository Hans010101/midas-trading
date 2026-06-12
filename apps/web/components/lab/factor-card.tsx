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
import { isDivergentFinding } from '@/lib/structure-viz'
import { cn } from '@/lib/utils'

interface FactorCardProps {
  finding: FactorFinding
  label: string
  series: SparkPoint[] | null
}

export function FactorCard({ finding, label, series }: FactorCardProps) {
  const divergent = isDivergentFinding(finding)
  return (
    <div
      className={cn(
        'rounded-lg border bg-cream p-4 shadow-sm',
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
      <div className="mt-1 font-serif text-base font-bold text-foreground">{finding.state}</div>
      {series !== null && <Sparkline data={series} />}
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{finding.detail}</p>
    </div>
  )
}
