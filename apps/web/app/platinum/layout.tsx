import type { Metadata } from 'next'

// SEO 批3:platinum 是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (告别全站同名 title · 纯透传零 UI 侵入)。canonical 不设(避免污染子路由 · 工具页非搜索着陆主力)。
export const metadata: Metadata = {
  title: '自动策略',
  description: '账户工具自助面板。',
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
