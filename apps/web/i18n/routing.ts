/**
 * i18n locale 常量(cookie 模式 · 无 [locale] 路由)。
 *
 * ★方案定案(2026-07-16 · 复活英文版前端激活):放弃 as-needed [locale] 路由
 *   (历史 4 次翻车:两次生产 redirect loop + 两次 SSG 页翻倍撞内存墙),改 cookie-locale——
 *   URL 不变、middleware 逐字节零改、无 [locale] 段,结构性消除上述两类事故。
 *   locale 从 NEXT_LOCALE cookie 取(见 request.ts / lib/i18n/locale-cookie.ts)。
 *
 * ★本文件【只放纯常量】(zh/en 两端都 import):不得引入 next/headers 等服务端专用模块,
 *   否则 client 组件 import 会炸。
 */
export const locales = ['zh', 'en'] as const
export type Locale = (typeof locales)[number]
export const defaultLocale: Locale = 'zh'

/** 客户端 + 服务端共用的 locale cookie 名(1 年 · 非 HttpOnly · 客户端需读写)。 */
export const LOCALE_COOKIE = 'NEXT_LOCALE'

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (locales as readonly string[]).includes(value)
}
