import type { Metadata } from 'next'

// SEO 批3:lab 是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (告别全站同名 title · 纯透传零 UI 侵入)。canonical 不设(避免污染子路由 · 工具页非搜索着陆主力)。
export const metadata: Metadata = {
  title: '策略研究室',
  description: '策略回测研究室 + AI 沙盘助手:用历史行情验证策略想法、结构诊断看懂市场。',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
