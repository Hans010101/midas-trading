import type { NextConfig } from 'next'

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

export default nextConfig
