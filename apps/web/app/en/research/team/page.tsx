import type { Metadata } from 'next'

import { JsonLd } from '@/components/seo/json-ld'
import { PublicProse, PublicSiteShell } from '@/components/seo/public-site-shell'
import { researchTeamSchema } from '@/lib/seo/schema'

export const metadata: Metadata = {
  title: 'Midas Trading Research Team',
  description: 'Organizational authorship, research scope and editorial responsibility for Midas Trading public content.',
  alternates: {
    canonical: '/en/research/team',
    languages: { 'zh-CN': '/research/team', en: '/en/research/team', 'x-default': '/research/team' },
  },
  openGraph: { title: 'Midas Trading Research Team', url: '/en/research/team' },
}

export default function EnglishResearchTeamPage() {
  return (
    <PublicSiteShell english>
      <JsonLd data={researchTeamSchema} />
      <PublicProse>
        <h1 className="font-serif text-3xl font-bold">Midas Trading Research Team</h1>
        <p>This is the organizational byline for the Midas Trading Academy, glossary, methodology and market-explanation content. It does not represent a fictional individual expert.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">Scope</h2>
        <p>The team covers market foundations, technical indicators, Chan Theory structure, perpetual-contract data, strategy backtesting, trading plans and review processes. Product engineering maintains data pipelines and deterministic calculations; editorial maintenance owns curriculum structure, factual review and Chinese–English consistency.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">Role of AI</h2>
        <p>AI may assist with synthesis, translation and clarity, but it does not replace sources, formulas or editorial responsibility. Public content remains anchored to version history, traceable sources and deterministic rules.</p>
        <h2 className="pt-4 font-serif text-xl font-bold">Corrections</h2>
        <p>Registered users can report factual, translation or product issues through Support Tickets. Confirmed issues are corrected in the source content.</p>
      </PublicProse>
    </PublicSiteShell>
  )
}
