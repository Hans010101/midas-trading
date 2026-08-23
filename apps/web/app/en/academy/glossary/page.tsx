import type { Metadata } from 'next'

import { ArticleRenderer } from '@/components/academy/article-renderer'
import { JsonLd } from '@/components/seo/json-ld'
import { PublicSiteShell } from '@/components/seo/public-site-shell'
import { getGlossary } from '@/lib/academy'
import { buildGlossaryTermSet } from '@/lib/academy/glossary-schema'

export const metadata: Metadata = {
  title: 'Trading Glossary · 88 essential terms',
  description: 'Concise English definitions for 88 trading and market-analysis terms across 10 categories.',
  alternates: {
    canonical: '/en/academy/glossary',
    languages: { 'zh-CN': '/academy/glossary', en: '/en/academy/glossary', 'x-default': '/academy/glossary' },
  },
  openGraph: { title: 'Trading Glossary · Midas Academy', url: '/en/academy/glossary' },
}

export default function EnglishGlossaryPage() {
  return <PublicSiteShell english><JsonLd data={buildGlossaryTermSet('en')} /><article className="mx-auto max-w-[72ch]"><ArticleRenderer markdown={getGlossary('en')} locale="en" /></article></PublicSiteShell>
}
