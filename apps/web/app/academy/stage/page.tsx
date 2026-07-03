/**
 * 某阶文章列表页 · 薄 server 壳(照 app/lab/report/page.tsx + crypto-preview/page.tsx 范式)。
 * <Suspense> 包 'use client' 的 <StageList/>(内部 useSearchParams 读 ?s={stageSlug})。
 * ⛔ 不建 [id] 动态路由段 —— 走 searchParams(项目零先例)。
 */

import { Suspense } from 'react'

import { StageList } from '@/components/academy/stage-list'

export default function AcademyStagePage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-background" />}>
      <StageList />
    </Suspense>
  )
}
