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
export const RESEARCH_TEAM_ID = `${BASE}/research/team#research-team`

/** Organization —— 品牌实体(landing 定义 · about 用同 @id 关联 · 让知识图谱归拢站点)。 */
export const organizationSchema = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  '@id': ORG_ID,
  name: 'Midas Trading',
  alternateName: ['点金 Midas', 'Midas'],
  url: BASE,
  logo: `${BASE}/brand/seal.png`,
  description:
    '覆盖加密、美股、A 股、港股四大市场的 AI 原生分析终端;全程虚拟资金,分析内容仅供参考,不构成投资建议。',
  sameAs: ['https://github.com/Hans010101/midas-trading'],
  knowsAbout: ['加密货币市场', '美股', 'A 股', '港股', '技术分析', '缠论', '策略回测'],
} as const

/** WebSite —— 站点实体(publisher 指向 Organization)。 */
export const websiteSchema = {
  '@context': 'https://schema.org',
  '@type': 'WebSite',
  '@id': WEBSITE_ID,
  name: 'Midas Trading',
  alternateName: '点金 Midas',
  url: BASE,
  inLanguage: ['zh-CN', 'en'],
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
  locale?: 'zh' | 'en'
}) {
  const english = input.locale === 'en'
  const url = `${BASE}${english ? '/en' : ''}/academy/article/${input.slug}`
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: input.title,
    description: input.excerpt,
    inLanguage: english ? 'en' : 'zh-CN',
    url,
    mainEntityOfPage: url,
    author: { '@id': RESEARCH_TEAM_ID },
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
  locale?: 'zh' | 'en'
}) {
  const prefix = input.locale === 'en' ? '/en' : ''
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      {
        '@type': 'ListItem',
        position: 1,
        name: input.locale === 'en' ? 'Academy' : '训练营',
        item: `${BASE}${prefix}/academy`,
      },
      {
        '@type': 'ListItem',
        position: 2,
        name: input.stageName,
        item: `${BASE}${prefix}/academy/stage/${input.stageSlug}`,
      },
      {
        '@type': 'ListItem',
        position: 3,
        name: input.title,
        item: `${BASE}${prefix}/academy/article/${input.slug}`,
      },
    ],
  }
}

export const researchTeamSchema = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  '@id': RESEARCH_TEAM_ID,
  name: 'Midas Trading 研究团队',
  alternateName: 'Midas Trading Research Team',
  url: `${BASE}/research/team`,
  parentOrganization: { '@id': ORG_ID },
  knowsAbout: ['市场数据研究', '技术分析', '缠论结构', '策略回测', '交易教育'],
} as const
