/**
 * 训练营内容读取工具 · ⚠️ server-only(含 node:fs · 只能在 server component / server 壳调用;
 * 误导入进 'use client' 组件 → next build 会报 "Module not found: Can't resolve 'fs'")。
 *
 * - 文章正文:content/academy/articles/{slug}.md(无 frontmatter · 首行即 `# 标题`)。
 * - 词典:content/academy/glossary.md。
 * - 列表 / 导航 / 上下篇元数据复用 manifest.ts(ACADEMY_STAGES / ACADEMY_ARTICLES)。
 *
 * cwd 约定:dev(`pnpm --filter @midas/web dev`)/ build(`cd apps/web && next build`)/
 *   prod(runner WORKDIR=/repo/apps/web · `next start`)三处 cwd 均为 apps/web,
 *   故 content 路径用 process.cwd() 拼接稳定可达(Dockerfile 整目录入镜像 · 非 standalone)。
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  ACADEMY_ARTICLES,
  ACADEMY_STAGES,
  type AcademyArticle,
  type AcademyStage,
} from '@/content/academy/manifest'

import { parseGlossaryTerms, buildSortedAliases, type AliasEntry } from './glossary-terms'

const ACADEMY_DIR = join(process.cwd(), 'content', 'academy')
const ARTICLES_DIR = join(ACADEMY_DIR, 'articles')
const GLOSSARY_PATH = join(ACADEMY_DIR, 'glossary.md')

/** 读单篇文章原始 markdown;slug 非法 / 文件缺失 → 返回 null(调用方出「文章不存在」)。 */
export function getArticleBySlug(slug: string): string | null {
  const meta = ACADEMY_ARTICLES.find((a) => a.slug === slug)
  if (!meta) return null
  try {
    return readFileSync(join(ARTICLES_DIR, meta.file), 'utf8')
  } catch {
    return null
  }
}

/** 读词典原始 markdown(词典本身含目录 + 8 大类 + 66 条)。 */
export function getGlossary(): string {
  return readFileSync(GLOSSARY_PATH, 'utf8')
}

let _glossaryAliasesCache: AliasEntry[] | null = null

/** 读 content/academy/glossary.md → 派生 别名→id(按长度降序),模块级缓存只解析一次 */
export function getGlossaryAliases(): AliasEntry[] {
  if (_glossaryAliasesCache) return _glossaryAliasesCache
  const md = readFileSync(GLOSSARY_PATH, 'utf8')
  _glossaryAliasesCache = buildSortedAliases(parseGlossaryTerms(md))
  return _glossaryAliasesCache
}

/** 篇目元数据(标题 / 阶 / order / excerpt)· 用于面包屑 / 校验存在。 */
export function getArticleMeta(slug: string): AcademyArticle | undefined {
  return ACADEMY_ARTICLES.find((a) => a.slug === slug)
}

/** 阶元数据(名称 / 阶标签 / 简介)。 */
export function getStage(slug: string): AcademyStage | undefined {
  return ACADEMY_STAGES.find((s) => s.slug === slug)
}

/** 同阶内上一篇 / 下一篇(按 order 升序)· 用于文章页底部导航。 */
export function getAdjacentArticles(slug: string): {
  prev: AcademyArticle | null
  next: AcademyArticle | null
} {
  const meta = getArticleMeta(slug)
  if (!meta) return { prev: null, next: null }
  const siblings = ACADEMY_ARTICLES.filter((a) => a.stage === meta.stage).sort(
    (a, b) => a.order - b.order,
  )
  const idx = siblings.findIndex((a) => a.slug === slug)
  return {
    prev: idx > 0 ? siblings[idx - 1] : null,
    next: idx >= 0 && idx < siblings.length - 1 ? siblings[idx + 1] : null,
  }
}
