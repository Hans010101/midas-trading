import type { Metadata } from 'next'
import { cookies } from 'next/headers'

import { LOCALE_COOKIE } from '@/i18n/routing'

// 财经日历是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (照 crypto-market 范式 · 纯透传零 UI 侵入)。
export async function generateMetadata(): Promise<Metadata> {
  const english = (await cookies()).get(LOCALE_COOKIE)?.value === 'en'
  return {
    title: {
      absolute: english ? 'Economic Calendar · Midas Trading' : '财经日历 · 点金 Midas',
    },
    description: english
      ? 'Official release schedule for FOMC decisions, payrolls, CPI, GDP, LPR and major central-bank events, shown in China Standard Time.'
      : '宏观经济事件日程一览:FOMC 议息、非农、CPI、GDP、LPR、央行决议等官方发布时间(北京时间)。',
    alternates: { canonical: '/calendar' },
    openGraph: {
      title: english ? 'Economic Calendar · Midas Trading' : '财经日历 · Midas Trading',
      url: '/calendar',
    },
  }
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
