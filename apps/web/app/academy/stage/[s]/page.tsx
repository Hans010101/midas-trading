/**
 * 某阶文章列表页 · server 页 · 路径段 /academy/stage/[s](SEO 批2)。
 *
 * ★由 ?s= 查询参数迁来(docs/decisions/0045 作废「零动态段」约定):server 端读 params.s 传
 *   props 给 <StageList/>(已去 useSearchParams)→ 消除 client bailout,阶描述 + 文章 <a> 列表
 *   进初始 HTML = 修审计 critical「stage 页空壳 · 118 篇文章爬虫孤岛」的枢纽一环。
 * generateStaticParams 6 阶全量 SSG + dynamicParams=false(未知阶构建期即 404)。
 * 旧 URL /academy/stage?s=x 由旧 page.tsx 薄壳 308 兜底。
 */

import type { Metadata } from 'next'

import { StageList } from '@/components/academy/stage-list'
import { ACADEMY_STAGES } from '@/content/academy/manifest'

export function generateStaticParams() {
  return ACADEMY_STAGES.map((s) => ({ s: s.slug }))
}
export const dynamicParams = false

export async function generateMetadata({
  params,
}: {
  params: Promise<{ s: string }>
}): Promise<Metadata> {
  const { s } = await params
  const stage = ACADEMY_STAGES.find((st) => st.slug === s)
  if (!stage) return {}
  const title = `${stage.stageLabel} ${stage.name} · 点金训练营`
  const canonical = `/academy/stage/${s}`
  return {
    title,
    description: stage.desc,
    alternates: { canonical },
    openGraph: { title, description: stage.desc, url: canonical },
  }
}

export default async function AcademyStagePage({
  params,
}: {
  params: Promise<{ s: string }>
}) {
  const { s } = await params
  return <StageList slug={s} />
}
