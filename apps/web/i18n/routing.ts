/**
 * i18n locale 常量(cookie-locale 无路由方案 · 决策 A · 见 docs/i18n/cookie-locale-design.md)。
 *
 * ★不再用 next-intl 的 defineRouting / localePrefix —— cookie 方案【不走路径路由】:
 *   locale 由 NEXT_LOCALE cookie 决定(i18n/request.ts),URL 恒不变、middleware 零参与、
 *   无 as-needed 隐形 rewrite → 批0 两次生产 redirect loop 的根源在此方案里物理不存在。
 *   本文件只作纯常量源(locales / defaultLocale / Locale 类型),供 request.ts 复用。
 */
export const locales = ['zh', 'en'] as const

export type Locale = (typeof locales)[number]

export const defaultLocale: Locale = 'zh'
