import type { Metadata } from 'next'

import { JsonLd } from '@/components/seo/json-ld'
import { PublicProse, PublicSiteShell } from '@/components/seo/public-site-shell'
import { organizationSchema } from '@/lib/seo/schema'

export const metadata: Metadata = {
  title: 'About',
  description: 'Product scope, principles and content model behind Midas Trading.',
  alternates: {
    canonical: '/en/about',
    languages: { 'zh-CN': '/about', en: '/en/about', 'x-default': '/about' },
  },
  openGraph: { title: 'About Midas Trading', url: '/en/about' },
}

export default function EnglishAboutPage() {
  return (
    <PublicSiteShell english>
      <JsonLd data={organizationSchema} />
      <PublicProse>
        <h1 className="font-serif text-3xl font-bold">About Midas Trading</h1>
        <p>Midas Trading is an independent, Cloudflare-native market analysis and trading education platform covering crypto, U.S., mainland China and Hong Kong markets.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">What the platform does</h2>
        <p>It combines public market data, technical indicators, derivatives metrics, Chan Theory structure, AI-assisted summaries, deterministic backtests and virtual trading tools in one workspace.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">How we think about analysis</h2>
        <p>Our goal is to describe observable structure—not to claim certainty about future prices. AI is used to organize and explain inputs; source data, timestamps and rule-based calculations remain the factual layer.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">Open education</h2>
        <p>The Academy and glossary are public and free. The English edition contains 118 structured lessons across six stages, from market foundations to technical analysis, derivatives, strategy design and disciplined execution.</p>
      </PublicProse>
    </PublicSiteShell>
  )
}
