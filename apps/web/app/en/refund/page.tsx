import type { Metadata } from 'next'

import { LegalP, LegalPage } from '@/components/legal/legal-page'

export const dynamic = 'force-static'

export const metadata: Metadata = {
  title: 'Free Service Notice',
  description: 'Midas Trading currently has no paid subscription, renewal or paid-feature checkout.',
  alternates: {
    canonical: '/en/refund',
    languages: { 'zh-CN': '/refund', en: '/en/refund', 'x-default': '/refund' },
  },
  openGraph: { title: 'Free Service Notice · Midas Trading', url: '/en/refund' },
}

export default function EnglishRefundPage() {
  return (
    <LegalPage title="Free Service Notice" english alternateHref="/refund">
      <LegalP>Midas Trading currently offers no paid subscriptions, automatic renewals or paid features. Registered users may use all available features free of charge, so there is currently no purchase or refund process.</LegalP>
      <LegalP>If you participated in an earlier test and have a related question, submit a support ticket through Contact Us.</LegalP>
    </LegalPage>
  )
}
