import type { Metadata } from 'next'
import localFont from 'next/font/local'

import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { QueryProvider } from '@/lib/providers/query-provider'
import { SessionProvider } from '@/lib/providers/session-provider'
import { ThemeProvider } from '@/lib/providers/theme-provider'
import { UiStoreProvider } from '@/lib/store/ui-store-provider'

import './globals.css'

// ── ADR 0030 · 字体本地化(防 Google Fonts 港/陆 build timeout) ──
// 字体来源 fontsource@5 / Google Fonts latin subset · woff2 总 ~143 KB · check in repo
// 视觉契约保持不变:与原 next/font/google 完全相同的字体名 / weight / subset(latin)
// CJK 字符仍走系统字体 fallback(跟原 subsets: ['latin'] 语义一致 · 不联网下载 CJK)
const notoSerifSC = localFont({
  variable: '--font-serif',
  display: 'swap',
  src: [
    { path: './fonts/noto-serif-sc-latin-400-normal.woff2', weight: '400', style: 'normal' },
    { path: './fonts/noto-serif-sc-latin-700-normal.woff2', weight: '700', style: 'normal' },
  ],
})

const notoSansSC = localFont({
  variable: '--font-sans',
  display: 'swap',
  src: [
    { path: './fonts/noto-sans-sc-latin-400-normal.woff2', weight: '400', style: 'normal' },
    { path: './fonts/noto-sans-sc-latin-500-normal.woff2', weight: '500', style: 'normal' },
    { path: './fonts/noto-sans-sc-latin-700-normal.woff2', weight: '700', style: 'normal' },
  ],
})

const jetbrainsMono = localFont({
  variable: '--font-mono',
  display: 'swap',
  src: [
    { path: './fonts/jetbrains-mono-latin-400-normal.woff2', weight: '400', style: 'normal' },
    { path: './fonts/jetbrains-mono-latin-500-normal.woff2', weight: '500', style: 'normal' },
    { path: './fonts/jetbrains-mono-latin-700-normal.woff2', weight: '700', style: 'normal' },
  ],
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
        {/* 涨跌色偏好 · 首屏前置脚本读 cookie 设 <html data-color-pref>(无闪烁 ·
            不依赖 SSR 读 cookie,故不破坏 / 等静态页的 force-static · 0023 §7)*/}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var m=document.cookie.match(/(?:^|; )color_pref=([^;]+)/);document.documentElement.dataset.colorPref=(m&&decodeURIComponent(m[1])==='green-up')?'green-up':'red-up';}catch(e){}})();",
          }}
        />
        <SessionProvider>
          <ThemeProvider>
            <QueryProvider>
              <UiStoreProvider>
                <TooltipProvider>{children}</TooltipProvider>
              </UiStoreProvider>
            </QueryProvider>
          </ThemeProvider>
        </SessionProvider>
        <Toaster position="top-center" closeButton />
      </body>
    </html>
  )
}
