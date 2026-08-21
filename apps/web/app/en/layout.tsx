import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: { template: '%s · Midas Trading', default: 'Midas Trading · AI-native market analysis' },
  description:
    'AI-native analysis for crypto, U.S., mainland China and Hong Kong markets, with market structure, strategy research and a free trading academy.',
  openGraph: { locale: 'en_US', siteName: 'Midas Trading' },
  twitter: {
    card: 'summary_large_image',
    title: 'Midas Trading · AI-native market analysis',
    description:
      'Cross-market data, technical structure, strategy research and a free 118-lesson trading academy.',
  },
}

export const dynamic = 'force-dynamic'

export default function EnglishLayout({ children }: { children: React.ReactNode }) {
  return children
}
