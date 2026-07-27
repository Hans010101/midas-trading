import type { MetadataRoute } from 'next'

import { ACADEMY_ARTICLES, ACADEMY_STAGES } from '@/content/academy/manifest'
import { DETAIL_MARKETS, DETAIL_SYMBOLS } from '@/lib/seo/detail-symbols'
import { PRODUCTION_WEB_URL } from '@/lib/site'

/**
 * sitemap.xml(SEO 批1 · docs/seo/2026-07-seo-geo-audit.md)。
 *
 * 覆盖 = 「server 端有真实内容或导航语义」的公开页:
 *   静态页(landing/市场页/功能页/训练营壳/法务)+ ★118 篇训练营文章(全站最大 SEO 资产 ·
 *   文章页 SSR 全文 · 此前是爬虫孤岛,sitemap 是让非 JS 爬虫拿到文章 URL 的最快通道)。
 * ★不进 sitemap:4 个 preview 详情页(?symbol= 变体是字节级相同的空壳,批7 做语义壳后再分批进)·
 *   login/register/verify-email(noindex 卫生页)· /academy/exam(纯交互)· admin/account(登录墙)。
 * ★文章/阶段 URL 已迁路径段(SEO 批2 · docs/decisions/0045):/academy/article/{slug} ·
 *   /academy/stage/{s} · 旧 ?slug=/?s= 由薄壳 308 兜底。
 * lastModified 不填(无可靠日期源 · D7 git 回填是批3 的事 · 宁缺毋假)。
 */

const BASE = PRODUCTION_WEB_URL

// 公开静态页(路径 · 相对权重)——与 app/ 目录实际路由对齐
const STATIC_PAGES: Array<[path: string, priority: number]> = [
  ['/', 1.0],
  ['/global', 0.8],
  ['/cn-market', 0.8],
  ['/us-market', 0.8],
  ['/hk-market', 0.8],
  ['/crypto-market', 0.8],
  ['/workbench', 0.7],
  ['/screener', 0.6],
  ['/watchlist', 0.5],
  ['/lab', 0.6],
  ['/lab/assistant', 0.5],
  ['/lab/report', 0.5],
  ['/platinum', 0.5],
  ['/academy', 0.9],
  ['/academy/glossary', 0.9],
  ['/calendar', 0.6],
  ['/about', 0.5],
  ['/privacy', 0.3],
  ['/terms', 0.3],
  ['/risk', 0.3],
]

export default function sitemap(): MetadataRoute.Sitemap {
  const staticEntries: MetadataRoute.Sitemap = STATIC_PAGES.map(([path, priority]) => ({
    url: `${BASE}${path}`,
    priority,
    changeFrequency: path === '/' ? 'weekly' : 'monthly',
  }))

  const stageEntries: MetadataRoute.Sitemap = ACADEMY_STAGES.map((s) => ({
    url: `${BASE}/academy/stage/${s.slug}`,
    priority: 0.7,
    changeFrequency: 'monthly',
  }))

  const articleEntries: MetadataRoute.Sitemap = ACADEMY_ARTICLES.map((a) => ({
    url: `${BASE}/academy/article/${a.slug}`,
    priority: 0.8,
    changeFrequency: 'monthly',
  }))

  // SEO 批7:详情页语义壳(路径段 · curated 有界集 · 4 市场)· 每 symbol 独立静态壳 + 唯一 title。
  // 旧 ?symbol= 空壳仍不进(非 curated 长尾)· curated 的旧 query 由 client redirect 兜到路径段。
  const detailEntries: MetadataRoute.Sitemap = DETAIL_MARKETS.flatMap((market) =>
    DETAIL_SYMBOLS[market].map((s) => ({
      url: `${BASE}/${market}/${s.symbol}`,
      priority: 0.6,
      changeFrequency: 'weekly' as const,
    })),
  )

  return [...staticEntries, ...detailEntries, ...stageEntries, ...articleEntries]
}
