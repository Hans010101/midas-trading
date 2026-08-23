/**
 * 词典 DefinedTermSet JSON-LD 构造(SEO 批3 · GEO 喂料)· server-only(fs 读 glossary.md)。
 *
 * ★88 词条「术语名 + 一句话定义」正是 AI 引擎最爱的 definition-lead 抽取偏好体(审计 GEO 镜头)。
 *   数据源唯一 = content/academy/glossary.md(与页面同源 · 解析 ### 标题 + `**一句话定义：**` 行)。
 */

import type { AcademyLocale } from '@/content/academy/localized-catalog'
import { getGlossary } from '@/lib/academy'
import { PRODUCTION_WEB_URL } from '@/lib/site'

const BASE = PRODUCTION_WEB_URL

interface GlossaryTerm {
  name: string
  definition: string
}

/** 解析中英文 glossary:每个三级标题 + 紧随其后的单句定义 → {name, definition}。 */
function parseGlossaryTerms(md: string, locale: AcademyLocale): GlossaryTerm[] {
  const terms: GlossaryTerm[] = []
  const lines = md.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const h = lines[i].match(/^###\s+\d+\.\s+(.+?)\s*$/)
    if (!h) continue
    // 去掉标题里的英文括号注释,取中文术语名(如「多头 / 做多 (Long)」→「多头 / 做多」)
    const name = locale === 'zh' ? h[1].replace(/\s*\([^)]*\)\s*$/, '').trim() : h[1].trim()
    // 向后找最近的「一句话定义」行
    let definition = ''
    for (let j = i + 1; j < Math.min(i + 8, lines.length); j++) {
      const d = lines[j].match(
        locale === 'zh'
          ? /\*\*一句话定义：\*\*\s*(.+?)\s*$/
          : /\*\*One-sentence definition:\*\*\s*(.+?)\s*$/i,
      )
      if (d) {
        definition = d[1].trim()
        break
      }
      if (/^###\s/.test(lines[j])) break // 撞到下一词条 · 停
    }
    if (name && definition) terms.push({ name, definition })
  }
  return terms
}

/** 构造 DefinedTermSet schema(hasDefinedTerm 每条指向词典页锚点)。 */
export function buildGlossaryTermSet(locale: AcademyLocale = 'zh') {
  const english = locale === 'en'
  const path = english ? '/en/academy/glossary' : '/academy/glossary'
  const termSetId = `${BASE}${path}#termset`
  const terms = parseGlossaryTerms(getGlossary(locale), locale)
  return {
    '@context': 'https://schema.org',
    '@type': 'DefinedTermSet',
    '@id': termSetId,
    name: english ? 'Midas Academy · Trading Glossary' : '点金训练营 · 交易名词词典',
    inLanguage: english ? 'en' : 'zh-CN',
    url: `${BASE}${path}`,
    hasDefinedTerm: terms.map((t) => ({
      '@type': 'DefinedTerm',
      name: t.name,
      description: t.definition,
      inDefinedTermSet: termSetId,
    })),
  }
}
