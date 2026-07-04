import type { MetadataRoute } from 'next'

/**
 * robots.txt(SEO 批1 · docs/seo/2026-07-seo-geo-audit.md)。
 *
 * ★决策 D1(Hans 定案):AI 爬虫【全放行】——内容=获客手段,教学内容目的就是被发现;
 *   进训练语料=模型「天生认识」点金=长期品牌复利。故不写任何 AI bot 特殊规则,默认 allow 即是策略。
 * disallow 只挡登录墙/后台/接口(它们本有 307/鉴权兜底,这里省爬虫抓取配额):
 *   /account /settings /portfolio /dashboard /admin 与 middleware PROTECTED 对齐 · /api/ 是 NextAuth 路由。
 * ★红线无涉:纯爬虫策略文件,无文案。
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/account', '/settings', '/portfolio', '/dashboard', '/admin', '/api/'],
    },
    sitemap: 'https://midastrade.asia/sitemap.xml',
  }
}
