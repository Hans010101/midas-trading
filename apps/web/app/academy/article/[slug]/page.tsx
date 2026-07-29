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
import { notFound } from 'next/navigation'

import { AcademyArticleContent } from '@/components/academy/academy-article-content'
import { JsonLd } from '@/components/seo/json-ld'
import { ARTICLE_DATES } from '@/lib/seo/article-dates'
import { buildArticleSchema, buildBreadcrumbSchema } from '@/lib/seo/schema'
import { ACADEMY_ARTICLES } from '@/content/academy/manifest'
import { getInteractives } from '@/content/academy/interactives'
import { getPractice, buildPracticeHref } from '@/content/academy/practice'
import { getQuiz } from '@/content/academy/quizzes'
import englishQuizzes from '@/content/academy/quizzes.en.json'
import type { QuizQuestion } from '@/content/academy/quizzes'
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
  const description = `${meta.excerpt}(${stage?.name ?? '点金训练营'})`
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
  const markdownEn = getArticleBySlug(slug, 'en')
  const meta = getArticleMeta(slug)
  const metaEn = getArticleMeta(slug, 'en')
  // dynamicParams=false 下 slug 必在 manifest;此分支纯防御(manifest 有条目但 md 文件缺失时真 404)
  if (!markdown || !markdownEn || !meta || !metaEn) notFound()
  const stage = getStage(meta.stage)
  const stageEn = getStage(metaEn.stage, 'en')
  const { prev, next } = getAdjacentArticles(slug)
  const adjacentEn = getAdjacentArticles(slug, 'en')
  const quiz = getQuiz(slug)
  const quizEn = (
    englishQuizzes as Record<string, QuizQuestion[]>
  )[slug] ?? []
  const practice = getPractice(slug)
  const interactives = getInteractives(slug)
  const glossaryAliases = getGlossaryAliases()

  const stageName = stage?.name ?? '点金训练营'

  return (
    <>
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
      <AcademyArticleContent
        slug={slug}
        zh={{ markdown, meta, stage, adjacent: { prev, next }, quiz }}
        en={{ markdown: markdownEn, meta: metaEn, stage: stageEn, adjacent: adjacentEn, quiz: quizEn }}
        practice={practice}
        practiceHref={practice ? buildPracticeHref(practice) : null}
        interactives={interactives}
        glossaryAliases={glossaryAliases}
      />
    </>
  )
}
