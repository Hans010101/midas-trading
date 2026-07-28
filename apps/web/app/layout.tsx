import type { Metadata } from 'next'
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages } from 'next-intl/server'
import localFont from 'next/font/local'

import { RewardToastWatcher } from '@/components/growth/reward-toast-watcher'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { QueryProvider } from '@/lib/providers/query-provider'
import { SessionProvider } from '@/lib/providers/session-provider'
import { PRODUCTION_WEB_URL } from '@/lib/site'
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

// 官网刀1:description 重写(加密打头 · 平等措辞 · 补港股 + 沙盘/回测关键词)
// + openGraph / twitter 卡(分享到 TG / X 出预览图)
export const metadata: Metadata = {
  metadataBase: new URL(PRODUCTION_WEB_URL),
  // SEO 批1:title 模板 —— 子页只写短 title,'%s · 点金 Midas' 统一品牌后缀(防手写漂移);
  // 未定义 title 的页面用 default(现状不变)。
  title: {
    template: '%s · 点金 Midas',
    default: '点金 Midas · AI 原生跨市场分析终端',
  },
  description:
    '覆盖加密、美股、A 股、港股四大市场的 AI 原生分析终端:11 因子结构沙盘、策略回测研究室、AI 决策卡与缠论自动标注。',
  openGraph: {
    title: '点金 Midas · AI 原生跨市场分析终端',
    description:
      '加密 · 美股 · A 股 · 港股四市场一屏俯瞰,AI 决策卡与缠论标注研判多空,沙盘看懂结构,研究室回测验证想法。',
    url: '/',
    siteName: '点金 Midas',
    images: [{ url: '/marketing/global.png', width: 1528, height: 951 }],
    locale: 'zh_CN',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: '点金 Midas · AI 原生跨市场分析终端',
    description:
      '加密 · 美股 · A 股 · 港股四市场 AI 分析终端:AI 决策卡 · 缠论标注 · 策略研究。',
    images: ['/marketing/global.png'],
  },
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // i18n(cookie 模式):locale + messages 从 request.ts(读 NEXT_LOCALE cookie)取。
  // force-static 页构建期 cookies() 无值 → locale=zh 静态(见 i18n/request.ts)。
  const locale = await getLocale()
  const messages = await getMessages()
  return (
    <html
      lang={locale === 'en' ? 'en' : 'zh-CN'}
      className={`${notoSerifSC.variable} ${notoSansSC.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body className="font-sans antialiased bg-background text-foreground">
        {/* OpenNext/esbuild 会给 next-themes 的首屏内联脚本注入 __name 调用,
            但浏览器内联上下文没有该 helper。先提供等价的 identity helper,
            避免主题初始化抛 ReferenceError；Function 构造器可防止构建器再次改写。 */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "globalThis.__name=globalThis.__name||Function('target','return target');",
          }}
        />
        {/* 涨跌色偏好 · 首屏前置脚本读 cookie 设 <html data-color-pref>(无闪烁 ·
            不依赖 SSR 读 cookie,故不破坏 / 等静态页的 force-static · 0023 §7)*/}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var m=document.cookie.match(/(?:^|; )color_pref=([^;]+)/);document.documentElement.dataset.colorPref=(m&&decodeURIComponent(m[1])==='green-up')?'green-up':'red-up';}catch(e){}})();",
          }}
        />
        <NextIntlClientProvider locale={locale} messages={messages}>
          <SessionProvider>
            <ThemeProvider>
              <QueryProvider>
                <UiStoreProvider>
                  <TooltipProvider>{children}</TooltipProvider>
                </UiStoreProvider>
              </QueryProvider>
            </ThemeProvider>
          </SessionProvider>
        </NextIntlClientProvider>
        {/* Phase 1.5 刀B:OAuth 到账 toast(读一次性 midas_reward cookie) */}
        <RewardToastWatcher />
        <Toaster position="top-center" closeButton />
      </body>
    </html>
  )
}
