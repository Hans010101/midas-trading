'use client'

/**
 * 模块结业测验入口 + 结业徽章 · 训练营 B 期刀2(client · 首页阶卡 + 阶列表页头共用)。
 *
 * 已结业(曾达标)→ 金色「🏆 已结业 · 可重考」;未结业 → 「结业测验」入口。
 * ★本刀只发结业荣誉,不发会员。未登录也显示入口(点进去再引导登录)。
 */

import { Award } from 'lucide-react'
import Link from 'next/link'

import { useExamResults } from '@/hooks/use-academy-exam'
import { cn } from '@/lib/utils'

export function StageExamEntry({
  stageSlug,
  className,
}: {
  stageSlug: string
  className?: string
}) {
  const { passedSet } = useExamResults()
  const graduated = passedSet.has(stageSlug)

  return (
    <Link
      href={`/academy/exam?stage=${stageSlug}`}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
        graduated
          ? 'border-gold/50 bg-gold/10 text-gold hover:bg-gold/20'
          : 'border-paper text-muted-foreground hover:border-gold/50 hover:text-gold',
        className,
      )}
    >
      <Award className="h-3.5 w-3.5" />
      {graduated ? '已结业 · 可重考' : '结业测验'}
    </Link>
  )
}
