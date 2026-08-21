import type { Metadata } from 'next'
import Link from 'next/link'

import { PublicSiteShell } from '@/components/seo/public-site-shell'
import { getAcademyArticles, getAcademyStages } from '@/content/academy/localized-catalog'

export const metadata: Metadata = {
  title: 'Academy · 118 free trading lessons',
  description: 'Six-stage trading curriculum with 118 English lessons and an 88-term glossary.',
  alternates: {
    canonical: '/en/academy',
    languages: { 'zh-CN': '/academy', en: '/en/academy', 'x-default': '/academy' },
  },
  openGraph: { title: 'Midas Academy · 118 free trading lessons', url: '/en/academy' },
}

export default function EnglishAcademyPage() {
  const stages = getAcademyStages('en')
  const articles = getAcademyArticles('en')
  return (
    <PublicSiteShell english>
      <section className="mb-8 max-w-3xl">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-midas-red">Midas Academy</p>
        <h1 className="mt-3 font-serif text-4xl font-bold">Build a trading process you can repeat</h1>
        <p className="mt-4 leading-7 text-muted-foreground">118 focused lessons across six stages, from market foundations to technical analysis, Chan Theory, derivatives, strategy design and disciplined execution.</p>
      </section>
      <div className="grid gap-4 sm:grid-cols-2">
        {stages.map((stage) => {
          const count = articles.filter((article) => article.stage === stage.slug).length
          return (
            <Link key={stage.slug} href={`/en/academy/stage/${stage.slug}`} className="rounded-xl border border-paper bg-cream p-5 transition-colors hover:border-midas-red/40">
              <span className="font-mono text-xs text-midas-red">{stage.stageLabel} · {count} lessons</span>
              <h2 className="mt-3 font-serif text-xl font-bold">{stage.name}</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{stage.desc}</p>
            </Link>
          )
        })}
      </div>
      <Link href="/en/academy/glossary" className="mt-5 block rounded-xl border border-gold/30 bg-background p-5 hover:border-gold">
        <h2 className="font-serif text-xl font-bold">Trading Glossary</h2>
        <p className="mt-1 text-sm text-muted-foreground">88 essential terms across 10 categories.</p>
      </Link>
    </PublicSiteShell>
  )
}
