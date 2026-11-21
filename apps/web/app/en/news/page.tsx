import type { Metadata } from 'next'

import { NewsTimeline, type NewsParams } from '@/components/news/industry-news'

export const dynamic = 'force-dynamic'
export const metadata: Metadata = {
  title: 'Market news',
  description: 'Headlines and primary releases across crypto, US, mainland China and Hong Kong stocks and macro policy, with publisher links and timestamps.',
  alternates: { canonical: '/en/news', languages: { 'zh-CN': '/news', en: '/en/news', 'x-default': '/news' } },
  openGraph: { title: 'Market news · Midas Trading', url: '/en/news' },
}

export default function Page({ searchParams }: { searchParams: NewsParams }) {
  return <NewsTimeline searchParams={searchParams} english />
}
