import type { Metadata } from 'next'

// SEO 批3:screener 是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (告别全站同名 title · 纯透传零 UI 侵入)。canonical 不设(避免污染子路由 · 工具页非搜索着陆主力)。
export const metadata: Metadata = {
  title: '选股筛选器',
  description: '按价格、涨跌幅、RSI、均线金叉等条件筛选 A股/美股/港股标的。筛选结果仅供参考,不构成投资建议。',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
