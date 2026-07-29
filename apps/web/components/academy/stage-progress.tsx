'use client'

/**
 * 某阶学习进度条 · 训练营 B 期刀1(刀1.5 调整分母)· 首页阶卡 + 阶列表页头共用。
 *
 * 登录后显示「已学 X/Y」+ 进度条(success 绿);未登录 / 数据未到 → 不渲染(只留 manifest 计数)。
 * ★分母 Y = 该阶【有小测】的文章数(刀1.5:答完小测=学完,无小测篇如 F36 不计);
 *   分子 X = 已完成的有小测文章数(从后端 completed_slugs 过滤)。见 academy-progress-calc。
 */

import { useAcademyProgress } from '@/hooks/use-academy-progress'
import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { stageQuizDone, stageQuizTotal } from '@/lib/academy-progress-calc'
import { cn } from '@/lib/utils'

export function StageProgress({
  stageSlug,
  className,
}: {
  stageSlug: string
  className?: string
}) {
  const { data, isLoggedIn } = useAcademyProgress()
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  if (!isLoggedIn || !data) return null // 未登录不显示进度(游客只看 manifest 计数)

  const total = stageQuizTotal(stageSlug)
  const done = stageQuizDone(data.completed_slugs, stageSlug)
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  const finished = total > 0 && done >= total

  return (
    <div className={cn('w-full', className)}>
      <div className="flex items-center justify-between text-[11px]">
        <span className={cn('font-medium', finished ? 'text-success' : 'text-muted-foreground')}>
          {en ? `Completed ${done}/${total}` : `已学 ${done}/${total}`}
        </span>
        {finished && (
          <span className="font-medium text-success">
            {en ? '✓ Complete' : '✓ 已学完'}
          </span>
        )}
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
