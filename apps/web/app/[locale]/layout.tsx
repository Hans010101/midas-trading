import { hasLocale, NextIntlClientProvider } from 'next-intl'
import { getMessages, setRequestLocale } from 'next-intl/server'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import localFont from 'next/font/local'

import { RewardToastWatcher } from '@/components/growth/reward-toast-watcher'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { routing } from '@/i18n/routing'
import { QueryProvider } from '@/lib/providers/query-provider'
import { SessionProvider } from '@/lib/providers/session-provider'
import { ThemeProvider } from '@/lib/providers/theme-provider'
import { UiStoreProvider } from '@/lib/store/ui-store-provider'

import '../globals.css'

// ── ADR 0030 · 字体本地化(防 Google Fonts 港/陆 build timeout) ──
// 字体来源 fontsource@5 / Google Fonts latin subset · woff2 总 ~143 KB · check in repo
// 视觉契约保持不变:与原 next/font/google 完全相同的字体名 / weight / subset(latin)
// CJK 字符仍走系统字体 fallback(跟原 subsets: ['latin'] 语义一致 · 不联网下载 CJK)
// ★i18n 激活:文件从 app/ 迁到 app/[locale]/ · 字体路径由 ./fonts → ../fonts(相对本文件)
const notoSerifSC = localFont({
  variable: '--font-serif',
  display: 'swap',
  src: [
    { path: '../fonts/noto-serif-sc-latin-400-normal.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/noto-serif-sc-latin-700-normal.woff2', weight: '700', style: 'normal' },
  ],
})

const notoSansSC = localFont({
  variable: '--font-sans',
  display: 'swap',
  src: [
    { path: '../fonts/noto-sans-sc-latin-400-normal.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/noto-sans-sc-latin-500-normal.woff2', weight: '500', style: 'normal' },
    { path: '../fonts/noto-sans-sc-latin-700-normal.woff2', weight: '700', style: 'normal' },
  ],
})

const jetbrainsMono = localFont({
  variable: '--font-mono',
  display: 'swap',
  src: [
    { path: '../fonts/jetbrains-mono-latin-400-normal.woff2', weight: '400', style: 'normal' },
    { path: '../fonts/jetbrains-mono-latin-500-normal.woff2', weight: '500', style: 'normal' },
    { path: '../fonts/jetbrains-mono-latin-700-normal.woff2', weight: '700', style: 'normal' },
  ],
})

// ★i18n 激活 + 构建内存修复(deploy-build-memory-wall):【只预渲染默认 locale zh】。
//   原返双 locale → 每页 SSG ×2(45→90)→ 生产 web build 静态生成内存压满整机(批0 翻车)。
//   改只返 zh:build SSG 数 = pre-批0 基线(45 页·已知能过的构建内存);英文页 dynamicParams
//   默认允许 → 按需 SSR 渲染(首访即时·不占构建内存)。中文=静态零回归,英文=按需。
export function generateStaticParams() {
  return [{ locale: routing.defaultLocale }]
}

// 官网刀1:description 重写 + openGraph / twitter 卡。
// ★i18n 激活:静态 metadata → generateMetadata(按 locale 出 lang / og.locale + hreflang alternates)。
//   ★文案(title/description)本刀暂沿用中文(SEO 文案翻译归批4 landing/SEO 域)· 批0 只保证
//   <html lang> / og:locale / hreflang 正确,不夹带 SEO 文案英译(混杂期已知项)。
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>
}): Promise<Metadata> {
  const { locale } = await params
  const isEn = locale === 'en'
  return {
    metadataBase: new URL('https://midastrade.asia'),
    title: '点金 Midas · AI 原生跨市场分析终端',
    description:
      '覆盖加密、美股、A 股、港股四大市场的 AI 原生分析终端:11 因子结构沙盘、策略回测研究室、AI 决策卡、缠论自动标注,Pro 会员解锁更高 AI 额度,全程虚拟资金,不构成投资建议。',
    openGraph: {
      title: '点金 Midas · AI 原生跨市场分析终端',
      description:
        '加密 · 美股 · A 股 · 港股四市场一屏俯瞰,AI 决策卡与缠论标注研判多空,沙盘看懂结构,研究室回测验证想法,Pro 会员更高额度,虚拟资金零风险实战。',
      url: isEn ? '/en' : '/',
      siteName: '点金 Midas',
      images: [{ url: '/marketing/global.png', width: 1528, height: 951 }],
      locale: isEn ? 'en_US' : 'zh_CN',
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title: '点金 Midas · AI 原生跨市场分析终端',
      description:
        '加密 · 美股 · A 股 · 港股四市场 AI 分析终端:AI 决策卡 · 缠论标注 · Pro 会员,全程虚拟资金。',
      images: ['/marketing/global.png'],
    },
    // ★hreflang:中英互为翻译(as-needed·中文根 / 英文 /en)· 避免搜索引擎判重复内容
    alternates: {
      languages: { zh: '/', en: '/en' },
    },
  }
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  // 非法 locale → 404(与 middleware 双保险)
  if (!hasLocale(routing.locales, locale)) {
    notFound()
  }
  // Next 15 静态渲染必须显式声明 locale,否则 request.ts 取不到、getMessages 报错
  setRequestLocale(locale)
  const messages = await getMessages()

  return (
    <html
      lang={locale}
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
        <NextIntlClientProvider messages={messages}>
          <SessionProvider>
            <ThemeProvider>
              <QueryProvider>
                <UiStoreProvider>
                  <TooltipProvider>{children}</TooltipProvider>
                </UiStoreProvider>
              </QueryProvider>
            </ThemeProvider>
          </SessionProvider>
          {/* Phase 1.5 刀B:OAuth 到账 toast(读一次性 midas_reward cookie) */}
          <RewardToastWatcher />
          <Toaster position="top-center" closeButton />
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
