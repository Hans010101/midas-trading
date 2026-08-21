import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { PublicSiteShell } from '@/components/seo/public-site-shell'
import { getAcademyArticles } from '@/content/academy/localized-catalog'
import { getStage } from '@/lib/academy'

export async function generateMetadata({ params }: { params: Promise<{ s: string }> }): Promise<Metadata> {
  const { s } = await params
  const stage = getStage(s, 'en')
  if (!stage) return {}
  const zh = `/academy/stage/${s}`
  const en = `/en/academy/stage/${s}`
  return {
    title: `${stage.name} · Midas Academy`,
    description: stage.desc,
    alternates: { canonical: en, languages: { 'zh-CN': zh, en, 'x-default': zh } },
    openGraph: { title: `${stage.name} · Midas Academy`, url: en },
  }
}

export default async function EnglishAcademyStagePage({ params }: { params: Promise<{ s: string }> }) {
  const { s } = await params
  const stage = getStage(s, 'en')
  if (!stage) notFound()
  const articles = getAcademyArticles('en').filter((article) => article.stage === s).sort((a, b) => a.order - b.order)
  return (
    <PublicSiteShell english>
      <nav className="mb-6 text-sm text-muted-foreground"><Link href="/en/academy" className="hover:text-midas-red">Academy</Link> / {stage.name}</nav>
      <p className="font-mono text-xs text-midas-red">{stage.stageLabel}</p>
      <h1 className="mt-2 font-serif text-3xl font-bold">{stage.name}</h1>
      <p className="mt-3 max-w-3xl leading-7 text-muted-foreground">{stage.desc}</p>
      <ol className="mt-8 divide-y divide-paper rounded-xl border border-paper bg-background">
        {articles.map((article, index) => (
          <li key={article.slug}>
            <Link href={`/en/academy/article/${article.slug}`} className="flex gap-4 p-4 hover:bg-surface-subtle">
              <span className="font-mono text-xs text-muted-foreground">{String(index + 1).padStart(2, '0')}</span>
              <span><strong className="font-medium">{article.title}</strong><span className="mt-1 block text-sm text-muted-foreground">{article.excerpt}</span></span>
            </Link>
          </li>
        ))}
      </ol>
    </PublicSiteShell>
  )
}
