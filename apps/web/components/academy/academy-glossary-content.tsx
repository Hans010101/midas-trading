'use client'

import { AcademySideNav } from '@/components/academy/academy-side-nav'
import { ArticleRenderer } from '@/components/academy/article-renderer'
import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { useAcademyDocumentTitle } from '@/hooks/use-academy-document-title'

export function AcademyGlossaryContent({
  markdownZh,
  markdownEn,
}: {
  markdownZh: string
  markdownEn: string
}) {
  const { locale } = useRuntimeLocale()
  useAcademyDocumentTitle({
    locale,
    english: 'Trading Glossary · 88 Essential Terms',
    chinese: '交易名词词典 · 88 条速查',
  })
  return (
    <div className="lg:flex lg:gap-8">
      <AcademySideNav active="glossary" />
      <div className="min-w-0 flex-1">
        <ArticleRenderer
          key={locale}
          markdown={locale === 'en' ? markdownEn : markdownZh}
          locale={locale}
        />
      </div>
    </div>
  )
}
