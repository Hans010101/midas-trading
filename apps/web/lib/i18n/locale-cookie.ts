/**
 * NEXT_LOCALE cookie 读写(cookie-locale 无路由方案 · 决策 A · docs/i18n/cookie-locale-design.md)。
 *
 * 单一真相源:i18n/request.ts 服务端读同名 cookie 决定渲染 locale;此处客户端读写。
 * ★持久化 1 年(非 session cookie · 关浏览器不丢)· SameSite=Lax · 非 HttpOnly(客户端要能写)。
 */
export const LOCALE_COOKIE = 'NEXT_LOCALE'

export type UiLocale = 'zh' | 'en'

const ONE_YEAR = 60 * 60 * 24 * 365

/** 写 NEXT_LOCALE cookie(客户端即时生效层 · 配合 router.refresh() 让服务端组件按新 locale 重渲)。 */
export function setLocaleCookie(locale: UiLocale): void {
  const secure = typeof location !== 'undefined' && location.protocol === 'https:' ? '; Secure' : ''
  document.cookie = `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=${ONE_YEAR}; SameSite=Lax${secure}`
}

/** 读 NEXT_LOCALE cookie · 无/非法 → 'zh'(与 request.ts 兜底一致 · 中文零破坏)。 */
export function getLocaleCookie(): UiLocale {
  if (typeof document === 'undefined') return 'zh'
  const m = document.cookie.match(/(?:^|; )NEXT_LOCALE=([^;]+)/)
  return m && decodeURIComponent(m[1]) === 'en' ? 'en' : 'zh'
}
