import createNextIntlPlugin from 'next-intl/plugin'
import type { NextConfig } from 'next'

// ★Phase 0 激活:挂 next-intl 插件,指向就绪的 i18n/request.ts(getRequestConfig 按 locale 载 messages)。
//   这是让 request.ts / routing.ts 骨架真正生效的唯一开关(未挂时它们是死骨架)。
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
