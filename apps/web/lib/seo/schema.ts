/**
 * JSON-LD schema 数据构造(SEO 批3)· 单一真相源 · 供 landing/about/文章页复用。
 *
 * ★红线:所有 description 走合规措辞(结构描述 · 免责 · 无买卖祈使词);author 用组织署名
 *   「点金 Midas 研究团队」(决策 D5 · 匿名保护)。★不加 WebSite.SearchAction —— 站内搜索是
 *   Cmd+K 客户端面板,无可爬的 /search?q= 结果页,硬加属误标(审计明确)。
 */

import { PRODUCTION_WEB_URL } from '@/lib/site'

const BASE = PRODUCTION_WEB_URL
export const ORG_ID = `${BASE}/#organization`
const WEBSITE_ID = `${BASE}/#website`

/** Organization —— 品牌实体(landing 定义 · about 用同 @id 关联 · 让知识图谱归拢站点)。 */
export const organizationSchema = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  '@id': ORG_ID,
  name: '点金 Midas',
  alternateName: 'Midas',
  url: BASE,
  logo: `${BASE}/brand/seal.png`,
  description:
    '覆盖加密、美股、A 股、港股四大市场的 AI 原生分析终端;全程虚拟资金,分析内容仅供参考,不构成投资建议。',
} as const

/** WebSite —— 站点实体(publisher 指向 Organization)。 */
export const websiteSchema = {
  '@context': 'https://schema.org',
  '@type': 'WebSite',
  '@id': WEBSITE_ID,
  name: '点金 Midas',
  url: BASE,
  inLanguage: 'zh-CN',
  publisher: { '@id': ORG_ID },
} as const

/** 文章 Article schema(每篇 · 喂富摘要 + AI 引擎引用)· date 由 GEO TL;DR刀 git 回填
 *  (见 lib/seo/article-dates.ts · AI 新鲜度信号)· 缺失仍走原「无日期」兜底(宁缺毋假)。 */
export function buildArticleSchema(input: {
  title: string
  excerpt: string
  slug: string
  stageName: string
  datePublished?: string
  dateModified?: string
}) {
  const url = `${BASE}/academy/article/${input.slug}`
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: input.title,
    description: `${input.excerpt}(${input.stageName} · 教学内容,仅供学习参考,不构成投资建议。)`,
    inLanguage: 'zh-CN',
    url,
    mainEntityOfPage: url,
    author: { '@type': 'Organization', name: '点金 Midas 研究团队' },
    publisher: { '@id': ORG_ID },
    image: `${BASE}/brand/seal.png`,
    // ★date 缺失时【不输出】该字段(保持原「无日期」兜底 · 宁缺毋假,绝不造假日期)。
    ...(input.datePublished ? { datePublished: input.datePublished } : {}),
    ...(input.dateModified ? { dateModified: input.dateModified } : {}),
  }
}

/** 面包屑 BreadcrumbList(训练营 > 阶 > 文章 · 已有可见面包屑 DOM · 此为其机器可读版)。 */
export function buildBreadcrumbSchema(input: {
  stageName: string
  stageSlug: string
  title: string
  slug: string
}) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: '训练营', item: `${BASE}/academy` },
      {
        '@type': 'ListItem',
        position: 2,
        name: input.stageName,
        item: `${BASE}/academy/stage/${input.stageSlug}`,
      },
      {
        '@type': 'ListItem',
        position: 3,
        name: input.title,
        item: `${BASE}/academy/article/${input.slug}`,
      },
    ],
  }
}
