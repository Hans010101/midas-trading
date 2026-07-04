import createNextIntlPlugin from 'next-intl/plugin'
import type { NextConfig } from 'next'

// ★cookie-locale i18n 激活(刀1 地基 · 决策 A · docs/i18n/cookie-locale-design.md):
//   挂 next-intl 插件指向 i18n/request.ts(按 NEXT_LOCALE cookie 载 messages)。
//   纯 cookie 无路由 —— 不建 [locale]/、middleware 零改、URL 恒不变、redirect loop 根源不存在。
const withNextIntl = createNextIntlPlugin('./i18n/request.ts')

const nextConfig: NextConfig = {
  transpilePackages: ['@midas/shared'],
  // typedRoutes 在动态路由 + NextAuth pages 字符串场景下摩擦过多
  // M0 阶段先关,后期 Task 7 视觉收尾时若仍需要再开
  typedRoutes: false,
  // 用户中心重组刀4:/settings 并入四模块 · permanent:false(迁移语义 · 留撤回余地)。
  // 兜后端 bot 三处链接(replies.py 免打扰菜单按钮 + 两条绑定文案 · 后端零碰)与旧书签;
  // /settings/wallet(历史资金页)单独精确指资产总览(资金管理语义)。
  async redirects() {
    return [
      { source: '/settings/wallet', destination: '/account', permanent: false },
      { source: '/settings', destination: '/account/alerts', permanent: false },
    ]
  },
}

export default withNextIntl(nextConfig)
