import type { Metadata } from 'next'
import Link from 'next/link'

import { PublicProse, PublicSiteShell } from '@/components/seo/public-site-shell'

export const metadata: Metadata = {
  title: 'Research methodology and data transparency',
  description: 'How Midas Trading handles market sources, update times, calculations, AI summaries, editorial review and corrections.',
  alternates: {
    canonical: '/en/research/methodology',
    languages: { 'zh-CN': '/research/methodology', en: '/en/research/methodology', 'x-default': '/research/methodology' },
  },
  openGraph: { title: 'Research methodology · Midas Trading', url: '/en/research/methodology' },
}

export default function EnglishMethodologyPage() {
  return (
    <PublicSiteShell english>
      <PublicProse>
        <h1 className="font-serif text-3xl font-bold">Research methodology and data transparency</h1>
        <p>This page explains how Midas Trading handles market data, calculations, AI-assisted analysis and educational content so readers and retrieval systems can evaluate provenance and freshness.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">Data layer</h2>
        <p>Market pages prioritize exchange, index and public-market interfaces. Available fields include price, volume, funding rate, open interest and long/short ratios. Visible source and update-time information takes precedence over generated commentary; unavailable upstream fields remain empty rather than being estimated.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">Calculation layer</h2>
        <p>Moving averages, MACD, RSI, Bollinger Bands, backtest results and Chan Theory structures are produced by deterministic rules. Backtests use completed historical windows and do not introduce future data into earlier observations.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">AI layer</h2>
        <p>AI organizes inputs, explains structure and writes readable summaries. It does not replace raw market data. Generated statements should trace back to visible data, a rule or a named public source; if the model is unavailable, the platform keeps the rule-based output instead of inventing a conclusion.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">Editorial process and corrections</h2>
        <p>The Midas Trading Research Team maintains the Academy curriculum. Article dates come from version history; missing dates are not fabricated. Verified factual, translation or methodology errors are corrected at the source and republished.</p>
        <p>See the <Link href="/en/research/team" className="text-midas-red hover:underline">research team profile</Link> and <Link href="/en/about" className="text-midas-red hover:underline">About Midas Trading</Link>.</p>
      </PublicProse>
    </PublicSiteShell>
  )
}
