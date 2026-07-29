'use client'

import { ChevronLeft, ChevronRight } from 'lucide-react'
import Link from 'next/link'

import { AcademySideNav } from '@/components/academy/academy-side-nav'
import { ArticleQuiz } from '@/components/academy/article-quiz'
import { ArticleRenderer } from '@/components/academy/article-renderer'
import { ArticleInteractives } from '@/components/academy/interactive/article-interactives'
import { PracticeCTA } from '@/components/academy/practice-cta'
import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { TopNav } from '@/components/layout/top-nav'
import type { InteractiveKey } from '@/content/academy/interactives'
import type { AcademyArticle, AcademyStage } from '@/content/academy/manifest'
import type { PracticeEntry } from '@/content/academy/practice'
import type { QuizQuestion } from '@/content/academy/quizzes'
import { useAcademyDocumentTitle } from '@/hooks/use-academy-document-title'
import type { AliasEntry } from '@/lib/glossary-terms'

type Adjacent = Readonly<{
  prev: AcademyArticle | null
  next: AcademyArticle | null
}>

export function AcademyArticleContent({
  slug,
  zh,
  en,
  practice,
  practiceHref,
  interactives,
  glossaryAliases,
}: {
  slug: string
  zh: {
    markdown: string
    meta: AcademyArticle
    stage: AcademyStage | undefined
    adjacent: Adjacent
    quiz: QuizQuestion[]
  }
  en: {
    markdown: string
    meta: AcademyArticle
    stage: AcademyStage | undefined
    adjacent: Adjacent
    quiz: QuizQuestion[]
  }
  practice: PracticeEntry | null
  practiceHref: string | null
  interactives: InteractiveKey[] | null
  glossaryAliases: AliasEntry[]
}) {
  const { locale } = useRuntimeLocale()
  const english = locale === 'en'
  const content = english ? en : zh
  const { meta, stage, adjacent, quiz, markdown } = content
  useAcademyDocumentTitle({
    locale,
    english: en.meta.title,
    chinese: zh.meta.title,
  })

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          <div className="lg:flex lg:gap-8">
            <AcademySideNav active={meta.stage} />
            <article className="min-w-0 flex-1">
              <nav
                className="mb-6 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground"
                aria-label={english ? 'Breadcrumb' : '面包屑'}
              >
                <Link href="/academy" className="transition-colors hover:text-midas-red">
                  {english ? 'Academy' : '训练营'}
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

              <div className={english ? 'max-w-[72ch]' : undefined}>
                <ArticleRenderer
                  key={`${slug}-${locale}`}
                  markdown={markdown}
                  glossaryAliases={english ? undefined : glossaryAliases}
                  locale={locale}
                />
              </div>

              {interactives && <ArticleInteractives keys={interactives} />}
              <ArticleQuiz key={`${slug}-${locale}`} questions={quiz} slug={slug} />

              {practice && practiceHref && (
                <PracticeCTA entry={practice} href={practiceHref} />
              )}

              <nav className="mt-10 flex items-stretch justify-between gap-3 border-t border-paper pt-6">
                {adjacent.prev ? (
                  <Link
                    href={`/academy/article/${adjacent.prev.slug}`}
                    className="group flex max-w-[48%] flex-col rounded-lg border border-paper p-3 transition-colors hover:border-midas-red/40"
                  >
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <ChevronLeft className="h-3 w-3" />
                      {english ? 'Previous' : '上一篇'}
                    </span>
                    <span className="mt-1 line-clamp-2 text-sm font-medium text-foreground transition-colors group-hover:text-midas-red">
                      {adjacent.prev.title}
                    </span>
                  </Link>
                ) : (
                  <span />
                )}
                {adjacent.next ? (
                  <Link
                    href={`/academy/article/${adjacent.next.slug}`}
                    className="group flex max-w-[48%] flex-col items-end rounded-lg border border-paper p-3 text-right transition-colors hover:border-midas-red/40"
                  >
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      {english ? 'Next' : '下一篇'}
                      <ChevronRight className="h-3 w-3" />
                    </span>
                    <span className="mt-1 line-clamp-2 text-sm font-medium text-foreground transition-colors group-hover:text-midas-red">
                      {adjacent.next.title}
                    </span>
                  </Link>
                ) : (
                  <span />
                )}
              </nav>
            </article>
          </div>
        </div>
      </main>
    </div>
  )
}
