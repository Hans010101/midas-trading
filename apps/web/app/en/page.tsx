import type { Metadata } from 'next'
import Link from 'next/link'

import { JsonLd } from '@/components/seo/json-ld'
import { PublicSiteShell } from '@/components/seo/public-site-shell'
import { organizationSchema, websiteSchema } from '@/lib/seo/schema'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'AI-native market analysis',
  alternates: {
    canonical: '/en',
    languages: { 'zh-CN': '/', en: '/en', 'x-default': '/' },
  },
  openGraph: { title: 'Midas Trading · AI-native market analysis', url: '/en' },
}

const FEATURES = [
  ['Cross-market dashboard', 'Track crypto, U.S., mainland China and Hong Kong markets in one workspace.'],
  ['Structure analysis', 'Combine price action, indicators, derivatives metrics and Chan Theory annotations.'],
  ['Strategy research', 'Backtest deterministic ideas and review results before using the virtual trading tools.'],
  ['Free academy', 'Learn through 118 English lessons and an 88-term trading glossary.'],
] as const

export default function EnglishHomePage() {
  return (
    <PublicSiteShell english>
      <JsonLd data={[organizationSchema, websiteSchema]} />
      <section className="rounded-2xl border border-paper bg-cream px-6 py-12 md:px-10">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-midas-red">AI-native market analysis</p>
        <h1 className="mt-3 max-w-3xl font-serif text-4xl font-bold leading-tight md:text-5xl">
          Read market structure. Test ideas. Build a repeatable process.
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-7 text-muted-foreground">
          Midas Trading brings multi-market data, technical structure, AI-assisted analysis,
          strategy research and virtual execution into one independent Cloudflare platform.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link href="/global" className="rounded-md bg-midas-red px-5 py-2.5 text-sm font-medium text-white">
            Open the terminal
          </Link>
          <Link href="/en/academy" className="rounded-md border border-midas-red px-5 py-2.5 text-sm font-medium text-midas-red">
            Explore the academy
          </Link>
        </div>
      </section>
      <section className="mt-8 grid gap-4 sm:grid-cols-2">
        {FEATURES.map(([title, description]) => (
          <div key={title} className="rounded-xl border border-paper bg-background p-5">
            <h2 className="font-serif text-lg font-bold">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
          </div>
        ))}
      </section>
    </PublicSiteShell>
  )
}
