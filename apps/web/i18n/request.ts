import { cookies } from 'next/headers'
import { headers } from 'next/headers'
import { getRequestConfig } from 'next-intl/server'

import { defaultLocale, isLocale, LOCALE_COOKIE, type Locale } from './routing'

/**
 * next-intl 每请求配置(cookie 模式 · 无 [locale] 路由)。
 *
 * locale 从 NEXT_LOCALE cookie 取:
 * - 动态页(workbench / account 等鉴权页 · 本就非 force-static):运行时读 cookie → zh/en。
 * - ★force-static 页(landing / 详情 / 法务 / 训练营 等):构建期 cookies() 无值 → 落
 *   defaultLocale(zh)静态,【不破坏 SSG】(这也是放弃 [locale] 路由改 cookie 的关键收益:
 *   force-static 页永远静态 zh · 只有动态页按 cookie 出 en · SSG 只 zh 基线 en 按需 dynamic)。
 *
 * 缺 key 时 next-intl 回退默认 locale(zh),配合 CI 缺 key 检测,避免线上露突兀语言。
 */
export default getRequestConfig(async () => {
  const routeLocale = (await headers()).get('x-midas-locale')
  const store = await cookies()
  const requested = store.get(LOCALE_COOKIE)?.value
  const locale: Locale = isLocale(routeLocale)
    ? routeLocale
    : isLocale(requested)
      ? requested
      : defaultLocale

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
