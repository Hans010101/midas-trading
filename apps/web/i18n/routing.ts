import { defineRouting } from 'next-intl/routing'

/**
 * i18n 路由配置(Phase 0 地基 · 决策 2 as-needed:中文 `/` 无前缀 · 英文 `/en`)。
 *
 * ★当前【未激活】:真正启用需 activation 三件——① next.config 挂 createNextIntlPlugin
 *   ② middleware.ts locale 检测/重写 ③ app/[locale]/ 页面迁移 + 根 layout 挂
 *   NextIntlClientProvider。这三件 touches next.config / layout / 全站页面,属"改全站组件/layout"
 *   的道(错层并行避让暗黑模式)。故本文件先作为【就绪骨架】存在,activation 延后到进场换 key 时统一做。
 */
export const routing = defineRouting({
  locales: ['zh', 'en'],
  defaultLocale: 'zh',
  localePrefix: 'as-needed',
})

export type Locale = (typeof routing.locales)[number]
