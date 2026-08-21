import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { ArticleRenderer } from '@/components/academy/article-renderer'
import { JsonLd } from '@/components/seo/json-ld'
import { PublicSiteShell } from '@/components/seo/public-site-shell'
import { ARTICLE_DATES } from '@/lib/seo/article-dates'
import { buildArticleSchema, buildBreadcrumbSchema } from '@/lib/seo/schema'
import { getAdjacentArticles, getArticleBySlug, getArticleMeta, getStage } from '@/lib/academy'

export const dynamic = 'force-dynamic'

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params
  const meta = getArticleMeta(slug, 'en')
  if (!meta) return {}
  const zh = `/academy/article/${slug}`
  const en = `/en/academy/article/${slug}`
  return {
    title: meta.title,
    description: meta.excerpt,
    alternates: { canonical: en, languages: { 'zh-CN': zh, en, 'x-default': zh } },
    openGraph: { title: meta.title, description: meta.excerpt, url: en, type: 'article' },
  }
}

export default async function EnglishAcademyArticlePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const markdown = getArticleBySlug(slug, 'en')
  const meta = getArticleMeta(slug, 'en')
  if (!markdown || !meta) notFound()
  const stage = getStage(meta.stage, 'en')
  const adjacent = getAdjacentArticles(slug, 'en')
  const stageName = stage?.name ?? 'Midas Academy'
  return (
    <PublicSiteShell english>
      <JsonLd data={[
        buildArticleSchema({ title: meta.title, excerpt: meta.excerpt, slug, stageName, locale: 'en', datePublished: ARTICLE_DATES[slug]?.published, dateModified: ARTICLE_DATES[slug]?.modified }),
        buildBreadcrumbSchema({ stageName, stageSlug: meta.stage, title: meta.title, slug, locale: 'en' }),
      ]} />
      <nav className="mb-7 text-sm text-muted-foreground"><Link href="/en/academy" className="hover:text-midas-red">Academy</Link> / <Link href={`/en/academy/stage/${meta.stage}`} className="hover:text-midas-red">{stageName}</Link></nav>
      <article className="mx-auto max-w-[72ch]"><ArticleRenderer markdown={markdown} locale="en" /></article>
      <nav className="mx-auto mt-10 flex max-w-[72ch] justify-between gap-4 border-t border-paper pt-6 text-sm">
        {adjacent.prev ? <Link href={`/en/academy/article/${adjacent.prev.slug}`} className="hover:text-midas-red">← {adjacent.prev.title}</Link> : <span />}
        {adjacent.next ? <Link href={`/en/academy/article/${adjacent.next.slug}`} className="text-right hover:text-midas-red">{adjacent.next.title} →</Link> : <span />}
      </nav>
    </PublicSiteShell>
  )
}
