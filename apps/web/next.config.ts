import type { NextConfig } from 'next'

// ★部署基建根治 阶段4:无害注释级改动·触发一次 web 重建走【默认 pull 链 + 镜像清理】验证
//   (Actions build+push → ACR → VPS docker compose pull → recreate·VPS 零构建负载·
//   7/7 pull 模式旧 sha 镜像催收在真机跑一次)。验证通过后可移除本行(纯占位·零功能影响)。
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
