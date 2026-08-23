import type { Metadata } from 'next'

import { LegalH2, LegalP, LegalPage } from '@/components/legal/legal-page'

export const dynamic = 'force-static'

export const metadata: Metadata = {
  title: 'Risk Notice',
  description: 'Midas Trading uses virtual funds only and does not provide investment advice or real trading.',
  alternates: {
    canonical: '/en/risk',
    languages: { 'zh-CN': '/risk', en: '/en/risk', 'x-default': '/risk' },
  },
  openGraph: { title: 'Risk Notice · Midas Trading', url: '/en/risk' },
}

export default function EnglishRiskPage() {
  return (
    <LegalPage title="Risk Notice" english alternateHref="/risk">
      <LegalP>Please read this notice before using Midas Trading. Using the platform means that you understand and accept these risks and limitations.</LegalP>
      <LegalH2>1. Virtual trading only</LegalH2>
      <LegalP>All orders, positions, balances, profits and losses are simulated with virtual funds. No operation is routed to a real market. Midas Trading is not a broker, exchange, custodian or clearing service, and simulated results do not represent real financial gains or losses.</LegalP>
      <LegalH2>2. Not investment advice</LegalH2>
      <LegalP>Market data, indicators, Chan Theory annotations, AI decision cards, strategy signals, backtests and educational content are for learning, research and reference only. They are not investment, financial or trading advice.</LegalP>
      <LegalP>AI outputs describe observable market structure and may contain errors, delays or omissions. They do not predict or guarantee future prices. Do not rely on the platform alone for real investment decisions; real markets can cause partial or total loss of capital.</LegalP>
      <LegalH2>3. Data and service limitations</LegalH2>
      <LegalP>Quotes come from third parties and may be delayed or inaccurate. Maintenance, network failures, provider outages or force majeure may interrupt data and features. We may change, suspend or discontinue services.</LegalP>
      <LegalH2>4. Acceptance of risk</LegalH2>
      <LegalP>To the maximum extent permitted by law, Midas Trading is not liable for direct, indirect, incidental or consequential loss arising from use or inability to use the platform. Its purpose is to support learning in a zero-real-capital-risk environment, not to promise returns.</LegalP>
    </LegalPage>
  )
}
