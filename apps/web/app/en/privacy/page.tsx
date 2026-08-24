import type { Metadata } from 'next'

import { LegalH2, LegalP, LegalPage, LegalUL } from '@/components/legal/legal-page'

export const dynamic = 'force-static'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'How Midas Trading collects, uses and protects account and service data.',
  alternates: {
    canonical: '/en/privacy',
    languages: { 'zh-CN': '/privacy', en: '/en/privacy', 'x-default': '/privacy' },
  },
  openGraph: { title: 'Privacy Policy · Midas Trading', url: '/en/privacy' },
}

export default function EnglishPrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" english alternateHref="/privacy">
      <LegalP>This policy explains what Midas Trading collects, why we use it and the rights available to you. Using the platform means that you understand these practices.</LegalP>
      <LegalH2>1. Information we collect</LegalH2>
      <LegalUL>
        <li>Account data such as your email address or mobile number, plus basic information authorized by a sign-in provider such as Google.</li>
        <li>Hashed passwords for email registration; we do not store or know your plaintext password.</li>
        <li>Support messages and attachments that you choose to submit.</li>
        <li>Virtual trades, virtual positions, watchlists, backtests, preferences and security logs needed to operate the service.</li>
      </LegalUL>
      <LegalP>Because this is a virtual-trading service, we do not request real bank, brokerage or exchange-account credentials, identity documents or facial data.</LegalP>
      <LegalH2>2. How we use information</LegalH2>
      <LegalP>We use data to create and secure accounts, provide virtual-trading and analysis features, maintain service reliability, answer support requests and improve the product. We do not sell personal information.</LegalP>
      <LegalH2>3. Service providers</LegalH2>
      <LegalP>Resend processes email delivery, Google processes Google sign-in, and Alibaba Cloud processes mobile numbers when sending SMS verification codes. Cloud and market-data providers support infrastructure and quotes. We share only what is necessary to provide the service or comply with applicable law.</LegalP>
      <LegalH2>4. Storage and security</LegalH2>
      <LegalP>Account, preference, alert and notification data is stored in this project’s independent Cloudflare D1 database. We use reasonable safeguards including password hashing and access controls, but no internet system can guarantee absolute security.</LegalP>
      <LegalH2>5. Your choices</LegalH2>
      <LegalP>You may review or update available account settings and request account deletion through Contact Us. Other rights apply as required by applicable law.</LegalP>
      <LegalH2>6. Cookies, age and updates</LegalH2>
      <LegalP>Cookies and local storage maintain sessions and preferences. The service is not intended for users below the applicable legal age. We may update this policy and will publish the revised version on this page.</LegalP>
    </LegalPage>
  )
}
