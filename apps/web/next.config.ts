import type { NextConfig } from 'next'
import createNextIntlPlugin from 'next-intl/plugin'

// i18n 激活(2026-07-16):挂 next-intl plugin,引用 cookie 模式的 request.ts(无 [locale] 路由)。
const withNextIntl = createNextIntlPlugin('./i18n/request.ts')

const nextConfig: NextConfig = {
  transpilePackages: ['@midas/shared'],
  // SEO 批5(docs/seo/2026-07-seo-geo-audit.md)三行优化:
  // ① 去 X-Powered-By: Next.js(减指纹·生产实测此头在发)
  poweredByHeader: false,
  // ② 关 Next 内建 gzip:压缩统一交给 Caddy(encode zstd gzip)。Next 只会 gzip,
  //    它压过之后 Caddy 对已编码响应直接透传 → zstd 永远轮不到;Next→Caddy 是同机
  //    loopback,未压缩传输零带宽成本。
  compress: false,
  // ③ /_next/image 优化器输出缓存 31 天(默认 60s)。当前训练营图走裸 <img> 不经优化器,
  //    此项为 webp 化(批5 评估结论:推迟到批2 落地后)预铺;favicon/og 等未来接入即受益。
  images: { minimumCacheTTL: 2678400 },
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
