import type { Metadata } from 'next'

import { LegalH2, LegalP, LegalPage, LegalUL } from '@/components/legal/legal-page'

export const dynamic = 'force-static'

export const metadata: Metadata = {
  title: 'Terms of Service',
  description: 'Terms governing use of the Midas Trading virtual-trading and education platform.',
  alternates: {
    canonical: '/en/terms',
    languages: { 'zh-CN': '/terms', en: '/en/terms', 'x-default': '/terms' },
  },
  openGraph: { title: 'Terms of Service · Midas Trading', url: '/en/terms' },
}

export default function EnglishTermsPage() {
  return (
    <LegalPage title="Terms of Service" english alternateHref="/terms">
      <LegalP>By registering for, accessing or using Midas Trading, you agree to these terms. If you do not agree, do not use the platform.</LegalP>
      <LegalH2>1. Service</LegalH2>
      <LegalP>Midas Trading is an AI-native market-analysis, education and virtual-trading tool covering crypto, U.S., mainland China and Hong Kong markets. Every trade uses virtual funds. The platform is not a broker, exchange, custodian or real-trading service, and its content is not investment advice.</LegalP>
      <LegalH2>2. Accounts</LegalH2>
      <LegalP>You may create and access an account by email, SMS or a third-party provider such as Google. You must provide accurate registration information, secure your credentials, meet the legal age requirements in your location and notify us of unauthorized access. We may suspend accounts that violate these terms.</LegalP>
      <LegalH2>3. Access and availability</LegalH2>
      <LegalP>Registered users may currently use all available features free of charge. We may apply uniform technical limits to protect reliability and may change, pause or restore features as operational needs require.</LegalP>
      <LegalH2>4. Acceptable use</LegalH2>
      <LegalUL>
        <li>Do not attack, disrupt or attempt unauthorized access to the platform or its data.</li>
        <li>Do not abuse automated requests, impersonate others or use the service unlawfully.</li>
      </LegalUL>
      <LegalH2>5. Intellectual property</LegalH2>
      <LegalP>Platform software, design, text, charts, analysis and branding are protected by applicable intellectual-property laws. Commercial copying, modification or distribution requires written permission.</LegalP>
      <LegalH2>6. Disclaimers and liability</LegalH2>
      <LegalP>The service is provided “as is.” To the maximum extent permitted by law, we do not guarantee accuracy, fitness, uninterrupted availability or error-free operation and are not liable for direct, indirect, incidental or consequential loss arising from use or inability to use the service.</LegalP>
      <LegalH2>7. Changes and governing law</LegalH2>
      <LegalP>Updated terms take effect when published. These terms are governed by the laws of the Hong Kong Special Administrative Region. If one provision is unenforceable, the remaining provisions continue in effect.</LegalP>
    </LegalPage>
  )
}
