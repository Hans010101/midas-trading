/**
 * 单篇文章页 · server component(不用 [id] 段,走 ?slug=)。
 *
 * server 端按 searchParams.slug 调 getArticleBySlug() 用 fs 读出原始 markdown,
 * 再把字符串作为 prop 传给 <ArticleRenderer/>('use client' · react-markdown 渲染)。
 * (思路同 /lab/report 薄 server 壳,但这里 server 端直接读文件 → 用 Next 15 的 searchParams Promise,
 *  无需 useSearchParams/Suspense。)
 *
 * 页面:TopNav + 面包屑(训练营 > 阶名 > 标题)+ 正文(md 首行即 h1)+ 上/下篇 + 免责页脚。
 * 找不到 slug → 友好「文章不存在」。全免费,无门控。
 */

import { ChevronLeft, ChevronRight, Home } from 'lucide-react'
import Link from 'next/link'

import { AcademySideNav } from '@/components/academy/academy-side-nav'
import { ArticleCompleteButton } from '@/components/academy/article-complete-button'
import { ArticleQuiz } from '@/components/academy/article-quiz'
import { ArticleRenderer } from '@/components/academy/article-renderer'
import { PracticeCTA } from '@/components/academy/practice-cta'
import { TopNav } from '@/components/layout/top-nav'
import { getPractice, buildPracticeHref } from '@/content/academy/practice'
import { getQuiz } from '@/content/academy/quizzes'
import {
  getAdjacentArticles,
  getArticleBySlug,
  getArticleMeta,
  getStage,
} from '@/lib/academy'

export default async function AcademyArticlePage({
  searchParams,
}: {
  searchParams: Promise<{ slug?: string }>
}) {
  const { slug = '' } = await searchParams
  const markdown = getArticleBySlug(slug)
  const meta = getArticleMeta(slug)
  const stage = meta ? getStage(meta.stage) : undefined
  const { prev, next } = getAdjacentArticles(slug)
  const quiz = getQuiz(slug)
  const practice = getPractice(slug)

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          <div className="lg:flex lg:gap-8">
            <AcademySideNav active={meta?.stage ?? ''} />
            <article className="min-w-0 flex-1">
          {!markdown || !meta ? (
            <div className="py-20 text-center">
              <p className="text-sm text-muted-foreground">文章不存在</p>
              <Link
                href="/academy"
                className="mt-3 inline-flex items-center gap-1 text-sm text-midas-red hover:underline"
              >
                <Home className="h-4 w-4" />
                返回训练营首页
              </Link>
            </div>
          ) : (
            <>
              {/* 面包屑 */}
              <nav className="mb-6 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <Link href="/academy" className="transition-colors hover:text-midas-red">
                  训练营
                </Link>
                {stage && (
                  <>
                    <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
                    <Link
                      href={`/academy/stage?s=${stage.slug}`}
                      className="transition-colors hover:text-midas-red"
                    >
                      {stage.name}
                    </Link>
                  </>
                )}
                <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
                <span className="text-foreground/70">{meta.title}</span>
              </nav>

              {/* 正文(markdown 首行即 # 标题 → ArticleRenderer 的 h1)*/}
              <ArticleRenderer markdown={markdown} />

              {/* 随堂小测(无题 → 组件返回 null,不渲染该区)*/}
              <ArticleQuiz questions={quiz} />

              {/* 去实战练入口(无配置 → 不渲染)*/}
              {practice && <PracticeCTA entry={practice} href={buildPracticeHref(practice)} />}

              {/* 标记学完(登录 toggle · 未登录引导登录)· 进度存后端 B 期刀1 */}
              <ArticleCompleteButton slug={slug} />

              {/* 上一篇 / 下一篇(同阶内按 order)*/}
              <nav className="mt-10 flex items-stretch justify-between gap-3 border-t border-paper pt-6">
                {prev ? (
                  <Link
                    href={`/academy/article?slug=${prev.slug}`}
                    className="group flex max-w-[48%] flex-col rounded-lg border border-paper p-3 transition-colors hover:border-midas-red/40"
                  >
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <ChevronLeft className="h-3 w-3" />
                      上一篇
                    </span>
                    <span className="mt-1 line-clamp-1 text-sm font-medium text-foreground transition-colors group-hover:text-midas-red">
                      {prev.title}
                    </span>
                  </Link>
                ) : (
                  <span />
                )}
                {next ? (
                  <Link
                    href={`/academy/article?slug=${next.slug}`}
                    className="group flex max-w-[48%] flex-col items-end rounded-lg border border-paper p-3 text-right transition-colors hover:border-midas-red/40"
                  >
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      下一篇
                      <ChevronRight className="h-3 w-3" />
                    </span>
                    <span className="mt-1 line-clamp-1 text-sm font-medium text-foreground transition-colors group-hover:text-midas-red">
                      {next.title}
                    </span>
                  </Link>
                ) : (
                  <span />
                )}
              </nav>

              {/* 免责页脚 */}
              <p className="mt-8 border-t border-paper pt-4 text-xs text-muted-foreground/60">
                教学内容,仅供学习参考,不构成投资建议。
              </p>
            </>
          )}
            </article>
          </div>
        </div>
      </main>
    </div>
  )
}
