import type { Metadata } from 'next'
import { cookies } from 'next/headers'

import { LOCALE_COOKIE } from '@/i18n/routing'

export async function generateMetadata(): Promise<Metadata> {
  const english = (await cookies()).get(LOCALE_COOKIE)?.value === 'en'
  const title = english ? 'AI Sandbox Assistant · Midas Trading' : 'AI 沙盘助手 · 点金 Midas'
  return {
    title: { absolute: title },
    alternates: { canonical: '/lab/assistant' },
    openGraph: { title, url: '/lab/assistant' },
    description: english
      ? 'A market-structure sandbox covering positioning, open interest, funding, basis, sentiment and order-book depth.'
      : '11 因子结构沙盘诊断:多空比、持仓量、资金费率等市场结构因子关联图谱 + AI 中文结构解读。',
  }
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
