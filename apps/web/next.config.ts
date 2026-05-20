import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  transpilePackages: ['@midas/shared'],
  // typedRoutes 在动态路由 + NextAuth pages 字符串场景下摩擦过多
  // M0 阶段先关,后期 Task 7 视觉收尾时若仍需要再开
  typedRoutes: false,
}

export default nextConfig
