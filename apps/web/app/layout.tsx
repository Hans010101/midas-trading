import type { ReactNode } from 'react'

/**
 * 根 layout · ★i18n 激活后退化为透传壳(next-intl [locale] 官方 pattern)。
 *
 * 原来这里塞的 <html>/<body> + 五个 Provider + 字体 + color-pref 脚本 + metadata
 * 全部下沉到 app/[locale]/layout.tsx(那层才知道当前 locale、才能设 <html lang={locale}>
 * 和挂 NextIntlClientProvider)。根 layout 不能再自己渲染 <html>/<body>,否则和 [locale]
 * layout 双重标签。它只负责把 children 透传给 [locale] 段。
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return children
}
