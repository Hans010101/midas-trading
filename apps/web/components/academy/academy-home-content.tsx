'use client'

import { ArrowRight, BookOpen, Compass, Layers3 } from 'lucide-react'
import Link from 'next/link'

import { StageGraduatedBadge } from '@/components/academy/stage-graduated-badge'
import { StageProgress } from '@/components/academy/stage-progress'
import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import {
  getAcademyArticles,
  getAcademyStages,
} from '@/content/academy/localized-catalog'
import { useAcademyDocumentTitle } from '@/hooks/use-academy-document-title'

export function AcademyHomeContent() {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const stages = getAcademyStages(locale)
  const articles = getAcademyArticles(locale)
  useAcademyDocumentTitle({
    locale,
    english: 'Academy · 118 Free Trading Lessons',
    chinese: '交易训练营 · 118 篇免费教学',
  })

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      {en && (
        <section className="mb-8 overflow-hidden rounded-2xl border border-paper bg-cream shadow-sm">
          <div className="grid gap-8 px-6 py-8 md:grid-cols-[1.45fr_0.8fr] md:px-8 md:py-10">
            <div>
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-midas-red">
                Midas Academy
              </p>
              <h1 className="mt-3 max-w-2xl text-balance font-serif text-3xl font-bold leading-tight text-foreground md:text-4xl">
                Build a trading process you can repeat
              </h1>
              <p className="mt-4 max-w-2xl text-pretty text-[15px] leading-7 text-muted-foreground">
                Move from market basics to technical analysis, Chan Theory, derivatives,
                strategy design, and disciplined execution—through 118 focused lessons.
              </p>
              <div className="mt-6 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="rounded-full border border-paper bg-background px-3 py-1.5">
                  6 learning stages
                </span>
                <span className="rounded-full border border-paper bg-background px-3 py-1.5">
                  118 lessons
                </span>
                <span className="rounded-full border border-paper bg-background px-3 py-1.5">
                  Quizzes & practice
                </span>
              </div>
            </div>
            <div className="flex flex-col justify-between rounded-xl border border-gold/25 bg-background/70 p-5">
              <Compass className="h-7 w-7 text-gold" />
              <div className="mt-10">
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                  Recommended path
                </p>
                <p className="mt-2 font-serif text-lg font-bold">Start with the foundations</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  Work through each stage in order, then use the quizzes to test recall.
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {stages.map((stage) => {
          const count = articles.filter((article) => article.stage === stage.slug).length
          return (
            <Link
              key={stage.slug}
              href={`/academy/stage/${stage.slug}`}
              className="group flex min-h-56 flex-col rounded-xl border border-paper bg-cream p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-midas-red/40 hover:shadow-md"
            >
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-midas-red/10 px-2.5 py-0.5 font-mono text-xs text-midas-red">
                  {stage.stageLabel}
                </span>
                <div className="flex items-center gap-2">
                  <StageGraduatedBadge stageSlug={stage.slug} />
                  <span className="text-xs text-muted-foreground/70">
                    {en ? `${count} lessons` : `共 ${count} 篇`}
                  </span>
                </div>
              </div>
              <h2 className="mt-3 text-balance font-serif text-lg font-bold">{stage.name}</h2>
              <p className="mt-2 flex-1 text-sm leading-6 text-muted-foreground">{stage.desc}</p>
              <StageProgress stageSlug={stage.slug} className="mt-4" />
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-midas-red">
                {en ? 'Explore stage' : '开始学习'}
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          )
        })}
      </div>

      <section className="mt-8">
        <div className="mb-4 flex items-center gap-2">
          {en && <Layers3 className="h-4 w-4 text-midas-red" />}
          <h2 className="font-serif text-lg font-bold">
            {en ? 'Start with these lessons' : '从这里开始读'}
          </h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {stages.map((stage) => {
            const top3 = articles
              .filter((article) => article.stage === stage.slug)
              .sort((a, b) => a.order - b.order)
              .slice(0, 3)
            return (
              <div key={stage.slug} className="rounded-xl border border-paper bg-cream p-4 shadow-sm">
                <p className="mb-2 font-mono text-xs text-midas-red">
                  {stage.stageLabel} · {stage.name}
                </p>
                <ul className="space-y-1.5">
                  {top3.map((article) => (
                    <li key={article.slug}>
                      <Link
                        href={`/academy/article/${article.slug}`}
                        className="line-clamp-1 text-sm text-foreground/80 transition-colors hover:text-midas-red"
                      >
                        {article.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </section>

      <Link
        href="/academy/glossary"
        className="mt-4 flex items-center gap-4 rounded-xl border border-paper bg-surface-subtle p-5 shadow-sm transition-colors hover:border-gold/50"
      >
        <BookOpen className="h-8 w-8 shrink-0 text-gold" />
        <div className="min-w-0 flex-1">
          <h2 className="font-serif text-lg font-bold">
            {en ? 'Trading Glossary' : '名词词典'}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {en
              ? '88 essential terms across 10 categories, with concise definitions and expanded notes.'
              : '88 个交易名词速查 · 10 大类 · 一句话定义 + 展开说明'}
          </p>
        </div>
        <ArrowRight className="h-5 w-5 shrink-0 text-muted-foreground/50" />
      </Link>
    </div>
  )
}
