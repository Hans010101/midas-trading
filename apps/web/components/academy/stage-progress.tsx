'use client'

/**
 * 某阶学习进度条 · 训练营 B 期刀1(client · 首页阶卡 + 阶列表页头共用)。
 *
 * 登录后显示「已学 X/Y」+ 进度条(success 绿);未登录 / 数据未到 → 不渲染(只留 manifest 计数)。
 * total 由调用方从 manifest 传(Y 的权威 · 与后端 stage_totals 一致)。
 */

import { useAcademyProgress } from '@/hooks/use-academy-progress'
import { cn } from '@/lib/utils'

export function StageProgress({
  stageSlug,
  total,
  className,
}: {
  stageSlug: string
  total: number
  className?: string
}) {
  const { data, isLoggedIn } = useAcademyProgress()
  if (!isLoggedIn || !data) return null // 未登录不显示进度(游客只看 manifest 计数)

  const done = data.by_stage[stageSlug] ?? 0
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  const finished = total > 0 && done >= total

  return (
    <div className={cn('w-full', className)}>
      <div className="flex items-center justify-between text-[11px]">
        <span className={cn('font-medium', finished ? 'text-success' : 'text-muted-foreground')}>
          已学 {done}/{total}
        </span>
        {finished && <span className="font-medium text-success">✓ 已学完</span>}
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-paper">
        <div
          className="h-full rounded-full bg-success transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
