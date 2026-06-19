/**
 * 训练营首页 · 列表页(server component · 无 hooks · 全免费无门控)。
 *
 * TopNav + 五阶概览卡片 + 词典入口卡片(★UI 修补:删二级标签行 + 大标题/副标题,直接从阶卡开始)。
 * 阶卡点击 → /academy/stage?s={slug};词典 → /academy/glossary。
 * ⛔ 不用 [id] 动态段;入口走查询参数(项目零先例规矩)。左侧导航只在内页(列表/详情/词典),首页不挂。
 */

import { ArrowRight, BookOpen } from 'lucide-react'
import Link from 'next/link'

import { StageProgress } from '@/components/academy/stage-progress'
import { TopNav } from '@/components/layout/top-nav'
import { ACADEMY_ARTICLES, ACADEMY_STAGES } from '@/content/academy/manifest'

export default function AcademyHomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          {/* 五阶概览 */}
          <div className="grid gap-4 sm:grid-cols-2">
            {ACADEMY_STAGES.map((stage) => {
              const count = ACADEMY_ARTICLES.filter((a) => a.stage === stage.slug).length
              return (
                <Link
                  key={stage.slug}
                  href={`/academy/stage?s=${stage.slug}`}
                  className="group flex flex-col rounded-xl border border-paper bg-cream p-5 shadow-sm transition-colors hover:border-midas-red/40"
                >
                  <div className="flex items-center justify-between">
                    <span className="rounded-full bg-midas-red/10 px-2.5 py-0.5 font-mono text-xs text-midas-red">
                      {stage.stageLabel}
                    </span>
                    <span className="text-xs text-muted-foreground/70">共 {count} 篇</span>
                  </div>
                  <h2 className="mt-3 font-serif text-lg font-bold">{stage.name}</h2>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                    {stage.desc}
                  </p>
                  {/* 学习进度(登录后显示已学 X/Y · 分母=有小测文章数 · B 期刀1.5)*/}
                  <StageProgress stageSlug={stage.slug} className="mt-4" />
                  <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-midas-red">
                    开始学习
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </Link>
              )
            })}
          </div>

          {/* 词典入口 */}
          <Link
            href="/academy/glossary"
            className="mt-4 flex items-center gap-4 rounded-xl border border-paper bg-surface-subtle p-5 shadow-sm transition-colors hover:border-gold/50"
          >
            <BookOpen className="h-8 w-8 shrink-0 text-gold" />
            <div className="min-w-0 flex-1">
              <h2 className="font-serif text-lg font-bold">名词词典</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                88 个交易名词速查 · 10 大类 · 一句话定义 + 展开说明
              </p>
            </div>
            <ArrowRight className="h-5 w-5 shrink-0 text-muted-foreground/50" />
          </Link>
        </div>
      </main>
    </div>
  )
}
