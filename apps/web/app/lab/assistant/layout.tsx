import type { Metadata } from 'next'
import { cookies } from 'next/headers'

import { LOCALE_COOKIE } from '@/i18n/routing'

// SEO 批3:lab/assistant 是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (告别全站同名 title · 纯透传零 UI 侵入)。canonical 不设(避免污染子路由 · 工具页非搜索着陆主力)。
export async function generateMetadata(): Promise<Metadata> {
  const english = (await cookies()).get(LOCALE_COOKIE)?.value === 'en'
  return {
    title: {
      absolute: english ? 'AI Sandbox Assistant · Midas Trading' : 'AI 沙盘助手 · 点金 Midas',
    },
    description: english
      ? 'A market-structure sandbox covering positioning, open interest, funding, basis, sentiment and order-book depth.'
      : '11 因子结构沙盘诊断:多空比、持仓量、资金费率等市场结构因子关联图谱 + AI 中文结构解读。',
  }
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
