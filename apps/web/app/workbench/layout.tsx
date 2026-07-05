import type { Metadata } from 'next'

// SEO 批3:workbench 是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (告别全站同名 title · 纯透传零 UI 侵入)。canonical 不设(避免污染子路由 · 工具页非搜索着陆主力)。
export const metadata: Metadata = {
  title: 'K 线工作台',
  description: '多市场 K 线工作台:MA/MACD/RSI/布林带指标、多周期图表、缠论自动标注与 AI 决策卡。分析仅供参考,不构成投资建议。',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
