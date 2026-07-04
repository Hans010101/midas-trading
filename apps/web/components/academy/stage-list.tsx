'use client'

/**
 * 某阶文章列表 · 'use client' 内层(stage/[s]/page.tsx server 页传 props slug · SEO 批2)。
 * ★去 useSearchParams 改 props:消除 client bailout → SSG 预渲染出完整 HTML(阶描述 + 文章
 *   <a> 列表进初始 HTML=打通「首页→阶→文章」纯 HTML 爬行链 · 修审计 critical「stage 空壳」)。
 * 仅用 manifest(纯数据 · 无 fs)过滤 + 按 order 排序;学习进度打勾(useAcademyProgress·登录态)
 * 留 client · SSR 首帧为未打勾态 · hydration 后补——这正是保留 'use client' 的唯一原因。
 *
 * UI 修补:删二级标签行 + 「‹ 训练营首页」返回链接;改为常驻左侧导航 AcademySideNav(active=当前阶 slug)。
 */

import { ArrowRight, CheckCircle2 } from 'lucide-react'
import Link from 'next/link'

import { AcademySideNav } from '@/components/academy/academy-side-nav'
import { StageExamEntry } from '@/components/academy/stage-exam-entry'
import { StageProgress } from '@/components/academy/stage-progress'
import { TopNav } from '@/components/layout/top-nav'
import { ACADEMY_ARTICLES, ACADEMY_STAGES } from '@/content/academy/manifest'
import { useAcademyProgress } from '@/hooks/use-academy-progress'

export function StageList({ slug }: { slug: string }) {
  const stage = ACADEMY_STAGES.find((s) => s.slug === slug)
  const articles = ACADEMY_ARTICLES.filter((a) => a.stage === slug).sort(
    (a, b) => a.order - b.order,
  )
  const { completedSet } = useAcademyProgress()

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          <div className="lg:flex lg:gap-8">
            <AcademySideNav active={slug} />
            <div className="min-w-0 flex-1">
              {!stage ? (
                <p className="py-16 text-center text-sm text-muted-foreground">阶段不存在</p>
              ) : (
                <>
                  <header className="mb-6">
                    <span className="rounded-full bg-midas-red/10 px-2.5 py-0.5 font-mono text-xs text-midas-red">
                      {stage.stageLabel}
                    </span>
                    <h1 className="mt-2 font-serif text-2xl font-bold">{stage.name}</h1>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {stage.desc}
                    </p>
                    {/* 本阶学习进度(登录后显示 · 分母=有小测文章数 · B 期刀1.5)*/}
                    <StageProgress stageSlug={slug} className="mt-4 max-w-xs" />
                    {/* 结业测验入口 + 结业徽章(B 期刀2 · 本刀只发荣誉)*/}
                    <StageExamEntry stageSlug={slug} className="mt-3" />
                  </header>

                  <ul className="space-y-2.5">
                    {articles.map((a) => (
                      <li key={a.slug}>
                        <Link
                          href={`/academy/article/${a.slug}`}
                          className="group flex items-start gap-3 rounded-lg border border-paper bg-cream p-4 shadow-sm transition-colors hover:border-midas-red/40"
                        >
                          {completedSet.has(a.slug) ? (
                            <span
                              title="已学完"
                              className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-success/15 text-success"
                            >
                              <CheckCircle2 className="h-4 w-4" />
                            </span>
                          ) : (
                            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-midas-red/10 font-mono text-xs text-midas-red">
                              {a.order}
                            </span>
                          )}
                          <div className="min-w-0 flex-1">
                            <h2 className="font-serif font-bold text-foreground transition-colors group-hover:text-midas-red">
                              {a.title}
                            </h2>
                            <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                              {a.excerpt}
                            </p>
                          </div>
                          <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-midas-red" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
