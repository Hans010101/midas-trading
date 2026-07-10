import type { Metadata } from 'next'

// 财经日历是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (照 crypto-market 范式 · 纯透传零 UI 侵入)。
export const metadata: Metadata = {
  title: '财经日历',
  description:
    '宏观经济事件日程一览:FOMC 议息、非农、CPI、GDP、LPR、央行决议等官方发布时间(北京时间)。仅供参考,不构成投资建议。',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
