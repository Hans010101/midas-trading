import type { Metadata } from 'next'

// SEO 批1:verify-email 是 'use client' 页(不能 export metadata)→ 路由段 layout 放 noindex
// (卫生页 · 无搜索价值 · 防以全站模板 title 进索引稀释质量信号)。零 UI 侵入,纯透传。
export const metadata: Metadata = {
  title: '邮箱验证',
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
