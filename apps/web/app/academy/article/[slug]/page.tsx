/**
 * 单篇文章页 · server component · 路径段 /academy/article/[slug](SEO 批2)。
 *
 * ★由 ?slug= 查询参数迁来(docs/decisions/0045 作废「零动态段」约定):
 *   generateStaticParams 118 篇全量 SSG(build 在 Actions·无内存墙)+ dynamicParams=false
 *   (未知 slug 构建期即 404 · 顺带根治旧版 200 软 404)。旧 URL 由旧 page.tsx 薄壳 308 兜底。
 * ★generateMetadata:每篇独立 title(模板自动补「· 点金 Midas」)+ description=excerpt +
 *   canonical —— 118 篇告别全站同名。
 *
 * 页面:TopNav + 面包屑(训练营 > 阶名 > 标题)+ 正文(md 首行即 h1)+ 上/下篇 + 免责页脚。
 * quiz/interactives/practice 注入只依赖 slug 值(与 URL 形态无关 · 侦察确认零回归)。全免费,无门控。
 */

import type { Metadata } from 'next'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { AcademySideNav } from '@/components/academy/academy-side-nav'
import { ArticleQuiz } from '@/components/academy/article-quiz'
import { ArticleRenderer } from '@/components/academy/article-renderer'
import { ArticleInteractives } from '@/components/academy/interactive/article-interactives'
import { PracticeCTA } from '@/components/academy/practice-cta'
import { TopNav } from '@/components/layout/top-nav'
import { JsonLd } from '@/components/seo/json-ld'
import { ARTICLE_DATES } from '@/lib/seo/article-dates'
import { buildArticleSchema, buildBreadcrumbSchema } from '@/lib/seo/schema'
import { ACADEMY_ARTICLES } from '@/content/academy/manifest'
import { getInteractives } from '@/content/academy/interactives'
import { getPractice, buildPracticeHref } from '@/content/academy/practice'
import { getQuiz } from '@/content/academy/quizzes'
import {
  getAdjacentArticles,
  getArticleBySlug,
  getArticleMeta,
  getGlossaryAliases,
  getStage,
} from '@/lib/academy'

// 118 篇全量 SSG · 未知 slug 构建期即 404(根治旧版 200 软 404)
export function generateStaticParams() {
  return ACADEMY_ARTICLES.map((a) => ({ slug: a.slug }))
}
export const dynamicParams = false

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  const meta = getArticleMeta(slug)
  if (!meta) return {}
  const stage = getStage(meta.stage)
  const description = `${meta.excerpt}(${stage?.name ?? '点金训练营'} · 教学内容,仅供学习参考,不构成投资建议。)`
  const canonical = `/academy/article/${slug}`
  return {
    title: meta.title,
    description,
    alternates: { canonical },
    openGraph: { title: meta.title, description, url: canonical },
  }
}

export default async function AcademyArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const markdown = getArticleBySlug(slug)
  const meta = getArticleMeta(slug)
  // dynamicParams=false 下 slug 必在 manifest;此分支纯防御(manifest 有条目但 md 文件缺失时真 404)
  if (!markdown || !meta) notFound()
  const stage = getStage(meta.stage)
  const { prev, next } = getAdjacentArticles(slug)
  const quiz = getQuiz(slug)
  const practice = getPractice(slug)
  const interactives = getInteractives(slug)
  const glossaryAliases = getGlossaryAliases()

  const stageName = stage?.name ?? '点金训练营'

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      {/* SEO 批3:Article + 面包屑 JSON-LD(喂富摘要 + AI 引擎引用)*/}
      <JsonLd
        data={[
          buildArticleSchema({
            title: meta.title, excerpt: meta.excerpt, slug, stageName,
            datePublished: ARTICLE_DATES[slug]?.published,
            dateModified: ARTICLE_DATES[slug]?.modified,
          }),
          buildBreadcrumbSchema({ stageName, stageSlug: meta.stage, title: meta.title, slug }),
        ]}
      />
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          <div className="lg:flex lg:gap-8">
            <AcademySideNav active={meta.stage} />
            <article className="min-w-0 flex-1">
              {/* 面包屑 */}
              <nav className="mb-6 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <Link href="/academy" className="transition-colors hover:text-midas-red">
                  训练营
                </Link>
                {stage && (
                  <>
                    <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
                    <Link
                      href={`/academy/stage/${stage.slug}`}
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
              <ArticleRenderer markdown={markdown} glossaryAliases={glossaryAliases} />

              {/* D 系列交互演示(无配置 → 不渲染)· 正文后、小测前 */}
              {interactives && <ArticleInteractives keys={interactives} />}

              {/* 随堂小测(无题 → 组件返回 null)· 刀1.5:选项洗牌 + 答完自动标记学完。
                  ★ key=slug:文章切换(soft nav)时强制重挂 → 重新洗牌 + 清空作答 */}
              <ArticleQuiz key={slug} questions={quiz} slug={slug} />

              {/* 去实战练入口(无配置 → 不渲染)*/}
              {practice && <PracticeCTA entry={practice} href={buildPracticeHref(practice)} />}

              {/* 上一篇 / 下一篇(同阶内按 order)*/}
              <nav className="mt-10 flex items-stretch justify-between gap-3 border-t border-paper pt-6">
                {prev ? (
                  <Link
                    href={`/academy/article/${prev.slug}`}
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
                    href={`/academy/article/${next.slug}`}
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
            </article>
          </div>
        </div>
      </main>
    </div>
  )
}
