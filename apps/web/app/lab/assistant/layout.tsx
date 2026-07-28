import type { Metadata } from 'next'

// SEO 批3:lab/assistant 是 'use client' 页(不能 export metadata)→ 路由段 layout 补独立 metadata
// (告别全站同名 title · 纯透传零 UI 侵入)。canonical 不设(避免污染子路由 · 工具页非搜索着陆主力)。
export const metadata: Metadata = {
  title: 'AI 沙盘助手',
  description: '11 因子结构沙盘诊断:多空比、持仓量、资金费率等市场结构因子关联图谱 + AI 中文结构解读。',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
