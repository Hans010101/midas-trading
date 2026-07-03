/**
 * 模块结业测验页 · 薄 server 壳(?stage=xxx · 零 [id] · 项目零先例规矩)。
 * <Suspense> 包 'use client' 的 <ExamRunner/>(内部 useSearchParams 读 ?stage)。
 */

import { Suspense } from 'react'

import { ExamRunner } from '@/components/academy/exam-runner'

export default function AcademyExamPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-background" />}>
      <ExamRunner />
    </Suspense>
  )
}
