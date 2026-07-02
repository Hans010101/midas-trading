import { getRequestConfig } from 'next-intl/server'

import { routing } from './routing'

/**
 * next-intl 每请求配置(按 locale 载入 messages)· Phase 0 就绪骨架。
 * ★未激活:被 next.config 的 createNextIntlPlugin 引用后才生效(见 routing.ts 说明)。
 * 缺 key 时 fallback 到默认 locale(zh),配合 CI 缺 key 检测,避免线上露突兀语言。
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale
  const locale = routing.locales.includes(requested as Locale)
    ? (requested as Locale)
    : routing.defaultLocale

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})

type Locale = (typeof routing.locales)[number]
