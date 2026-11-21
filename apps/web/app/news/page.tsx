import type { Metadata } from 'next'

import { NewsTimeline, type NewsParams } from '@/components/news/industry-news'

export const dynamic = 'force-dynamic'
export const metadata: Metadata = {
  title: '行业快讯',
  description: '按发布时间浏览加密、A 股、美股、港股与宏观政策快讯，查看新闻来源与原文。',
  alternates: { canonical: '/news', languages: { 'zh-CN': '/news', en: '/en/news', 'x-default': '/news' } },
  openGraph: { title: '行业快讯 · Midas Trading', url: '/news' },
}

export default function Page({ searchParams }: { searchParams: NewsParams }) {
  return <NewsTimeline searchParams={searchParams} />
}
