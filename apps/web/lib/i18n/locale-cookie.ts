/**
 * NEXT_LOCALE cookie 读写(客户端)· cookie 模式 locale 的唯一真源。
 *
 * - 服务端 i18n/request.ts 读同一 cookie 决定 SSR 的 messages/locale。
 * - 客户端语言切换写它 + router.refresh() 让 SSR 重渲染(URL 不变 · 无 [locale] 路由)。
 * - X-Lang 请求头也从它取(见 lib/i18n/lang-headers.ts),保证前后端同一 locale。
 */
import { defaultLocale, isLocale, LOCALE_COOKIE, type Locale } from '@/i18n/routing'

export function getLocaleCookie(): Locale {
  if (typeof document === 'undefined') return defaultLocale
  const match = document.cookie.match(new RegExp(`(?:^|; )${LOCALE_COOKIE}=([^;]+)`))
  const value = match ? decodeURIComponent(match[1]) : null
  return isLocale(value) ? value : defaultLocale
}

export function setLocaleCookie(locale: Locale): void {
  if (typeof document === 'undefined') return
  // 1 年 · path=/ · SameSite=Lax · 非 HttpOnly(客户端要读 · 服务端 request.ts 也读同一个)。
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; SameSite=Lax`
}
