/**
 * 训练营内容读取工具 · 正文在构建前机械同步为 JSON 内容映射,
 * 让 Cloudflare Worker 无需运行时文件系统即可读取全部课程。
 *
 * - 文章正文:content/academy/articles/{slug}.md(无 frontmatter · 首行即 `# 标题`)。
 * - 词典:content/academy/glossary.md。
 * - 列表 / 导航 / 上下篇元数据复用 manifest.ts(ACADEMY_STAGES / ACADEMY_ARTICLES)。
 *
 */
import {
  ACADEMY_ARTICLES,
  ACADEMY_STAGES,
  type AcademyArticle,
  type AcademyStage,
} from '@/content/academy/manifest'
import {
  ACADEMY_ARTICLES_EN,
  ACADEMY_STAGES_EN,
  type AcademyLocale,
} from '@/content/academy/localized-catalog'
import articlesEn from '@/content/academy/articles.en.json'
import articlesZh from '@/content/academy/articles.zh.json'
import glossaryEn from '@/content/academy/glossary.en.json'
import glossaryZh from '@/content/academy/glossary.zh.json'

import { parseGlossaryTerms, buildSortedAliases, type AliasEntry } from './glossary-terms'

/** 读单篇文章原始 markdown;slug 非法 / 文件缺失 → 返回 null(调用方出「文章不存在」)。 */
export function getArticleBySlug(slug: string, locale: AcademyLocale = 'zh'): string | null {
  const meta = ACADEMY_ARTICLES.find((a) => a.slug === slug)
  if (!meta) return null
  const articles = locale === 'en' ? articlesEn : articlesZh
  return (articles as Record<string, string>)[slug] ?? null
}

/** 读词典原始 markdown(词典本身含目录 + 8 大类 + 66 条)。 */
export function getGlossary(locale: AcademyLocale = 'zh'): string {
  return locale === 'en' ? glossaryEn.markdown : glossaryZh.markdown
}

let _glossaryAliasesCache: AliasEntry[] | null = null

/** 读 content/academy/glossary.md → 派生 别名→id(按长度降序),模块级缓存只解析一次 */
export function getGlossaryAliases(): AliasEntry[] {
  if (_glossaryAliasesCache) return _glossaryAliasesCache
  _glossaryAliasesCache = buildSortedAliases(parseGlossaryTerms(glossaryZh.markdown))
  return _glossaryAliasesCache
}

/** 篇目元数据(标题 / 阶 / order / excerpt)· 用于面包屑 / 校验存在。 */
export function getArticleMeta(
  slug: string,
  locale: AcademyLocale = 'zh',
): AcademyArticle | undefined {
  return (locale === 'en' ? ACADEMY_ARTICLES_EN : ACADEMY_ARTICLES).find((a) => a.slug === slug)
}

/** 阶元数据(名称 / 阶标签 / 简介)。 */
export function getStage(slug: string, locale: AcademyLocale = 'zh'): AcademyStage | undefined {
  return (locale === 'en' ? ACADEMY_STAGES_EN : ACADEMY_STAGES).find((s) => s.slug === slug)
}

/** 同阶内上一篇 / 下一篇(按 order 升序)· 用于文章页底部导航。 */
export function getAdjacentArticles(
  slug: string,
  locale: AcademyLocale = 'zh',
): {
  prev: AcademyArticle | null
  next: AcademyArticle | null
} {
  const meta = getArticleMeta(slug, locale)
  if (!meta) return { prev: null, next: null }
  const articles = locale === 'en' ? ACADEMY_ARTICLES_EN : ACADEMY_ARTICLES
  const siblings = articles.filter((a) => a.stage === meta.stage).sort(
    (a, b) => a.order - b.order,
  )
  const idx = siblings.findIndex((a) => a.slug === slug)
  return {
    prev: idx > 0 ? siblings[idx - 1] : null,
    next: idx >= 0 && idx < siblings.length - 1 ? siblings[idx + 1] : null,
  }
}
