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
  // ★localeDetection: false(批0 v2 生产 redirect loop 修 · 决定性):默认开时 next-intl 会对
  //   `/` 按 cookie/Accept-Language 重定向(首访无 NEXT_LOCALE cookie → 307 带 Set-Cookie),
  //   不持久化 cookie 的客户端(curl / 爬虫 / 健康检查 / 监控)每次都触发 → 撞成【`/`→307→`/`
  //   无限 loop】→ 中文站崩(生产 Caddy 反代下暴露·本地 next start 未复现)。关掉检测:
  //   `/` 恒服务默认 zh、永不因检测重定向(★中文零破坏最安全)· 英文只走显式 `/en`(语言切换器
  //   router.replace({locale}) 导航)· 初始 locale 由 URL 定,不做魔法自动跳转。
  localeDetection: false,
})

export type Locale = (typeof routing.locales)[number]
