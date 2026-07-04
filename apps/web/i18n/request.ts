import { cookies } from 'next/headers'
import { getRequestConfig } from 'next-intl/server'

import { defaultLocale, locales, type Locale } from './routing'

/**
 * next-intl 每请求配置(cookie-locale 无路由方案 · 决策 A · 见 docs/i18n/cookie-locale-design.md)。
 *
 * locale 由 NEXT_LOCALE cookie 决定(前端语言切换写 cookie · 刀2);无 / 非法值 → 默认 zh(★中文零破坏)。
 * ★读 cookies() 使【订阅 locale 的页】走 dynamic 渲染(Next.js Dynamic API 语义 · 设计 §1 已知取舍);
 *   force-static 页(/·privacy·terms·risk)在其上下文读不到 cookie → 自然回落 zh、保持静态。
 * ★middleware 完全不参与 → 无路由重写 / 无 307 → 批0 两次 redirect loop 的根源物理不存在。
 * 缺 key 时 next-intl fallback 到默认 locale(zh),避免线上露突兀语言。
 */
export default getRequestConfig(async () => {
  const store = await cookies()
  const requested = store.get('NEXT_LOCALE')?.value
  const locale: Locale = locales.includes(requested as Locale)
    ? (requested as Locale)
    : defaultLocale

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
