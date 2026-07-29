'use client'

/**
 * 结业徽章(纯状态指示 · 非链接)· 训练营 B 期刀2。
 *
 * 用于首页阶卡(整卡已是 <Link>,不能嵌 <Link> → 用 span 徽章);已结业才渲染金色「已结业」。
 * 完整「结业测验」入口在阶列表页(StageExamEntry)。
 */

import { Award } from 'lucide-react'

import { useExamResults } from '@/hooks/use-academy-exam'
import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'

export function StageGraduatedBadge({ stageSlug }: { stageSlug: string }) {
  const { passedSet } = useExamResults()
  const { locale } = useRuntimeLocale()
  if (!passedSet.has(stageSlug)) return null

  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-gold/50 bg-gold/10 px-2 py-0.5 text-[11px] font-medium text-gold">
      <Award className="h-3 w-3" />
      {locale === 'en' ? 'Graduated' : '已结业'}
    </span>
  )
}
