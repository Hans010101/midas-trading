import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: '回测报告',
  description: '个人策略回测报告。',
  alternates: { canonical: '/lab/report' },
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
