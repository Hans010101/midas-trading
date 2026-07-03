/**
 * 研究室回测报告页 · 薄 server 壳(P1-4d)。
 *
 * 照 app/crypto-preview/page.tsx:<Suspense> 包 'use client' 的 <LabReport/>(内部 useSearchParams 读 ?id=)。
 * ⛔ 不建 [id] 动态路由段 —— 项目零先例,首刀走 searchParams(逐字同 crypto-preview)。
 */

import { Suspense } from 'react'

import { LabReport } from '@/components/lab/lab-report'

export default function LabReportPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-background" />}>
      <LabReport />
    </Suspense>
  )
}
