import type { Metadata } from 'next'

// SEO 批3:global 是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (告别全站同名 title · 纯透传零 UI 侵入)。canonical 不设(避免污染子路由 · 工具页非搜索着陆主力)。
export const metadata: Metadata = {
  title: '全球市场',
  description: '全球主要市场指数一屏纵览:美股、A股、港股、加密实时指数概览。',
  alternates: { canonical: '/global' },
  openGraph: { title: '全球市场 · Midas Trading', url: '/global' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
