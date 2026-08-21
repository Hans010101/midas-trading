import type { Metadata } from 'next'

// SEO 批3:crypto-market 是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (告别全站同名 title · 纯透传零 UI 侵入)。canonical 不设(避免污染子路由 · 工具页非搜索着陆主力)。
export const metadata: Metadata = {
  title: '加密行情',
  description: '加密货币永续合约市场:主流币种实时价格、资金费率、持仓量与成交额榜单。',
  alternates: { canonical: '/crypto-market' },
  openGraph: { title: '加密行情 · Midas Trading', url: '/crypto-market' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
