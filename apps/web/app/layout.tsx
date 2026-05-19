import type { Metadata } from 'next'
import { JetBrains_Mono, Noto_Sans_SC, Noto_Serif_SC } from 'next/font/google'

import { QueryProvider } from '@/lib/providers/query-provider'
import { ThemeProvider } from '@/lib/providers/theme-provider'
import { UiStoreProvider } from '@/lib/store/ui-store-provider'

import './globals.css'

const notoSerifSC = Noto_Serif_SC({
  subsets: ['latin'],
  weight: ['400', '700'],
  variable: '--font-serif',
  display: 'swap',
})

const notoSansSC = Noto_Sans_SC({
  subsets: ['latin'],
  weight: ['400', '500', '700'],
  variable: '--font-sans',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '700'],
  variable: '--font-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: '点金 Midas · AI 原生跨市场分析终端',
  description: '面向 A 股 / 美股 / 加密的 AI 原生分析终端,仅虚拟资金交易',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html
      lang="zh-CN"
      className={`${notoSerifSC.variable} ${notoSansSC.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body className="font-sans antialiased bg-background text-foreground">
        <ThemeProvider>
          <QueryProvider>
            <UiStoreProvider>{children}</UiStoreProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
