/**
 * 词典 DefinedTermSet JSON-LD 构造(SEO 批3 · GEO 喂料)· server-only(fs 读 glossary.md)。
 *
 * ★88 词条「术语名 + 一句话定义」正是 AI 引擎最爱的 definition-lead 抽取偏好体(审计 GEO 镜头)。
 *   数据源唯一 = content/academy/glossary.md(与页面同源 · 解析 ### 标题 + `**一句话定义：**` 行)。
 */

import { getGlossary } from '@/lib/academy'
import { PRODUCTION_WEB_URL } from '@/lib/site'

const BASE = PRODUCTION_WEB_URL

interface GlossaryTerm {
  name: string
  definition: string
}

/** 解析 glossary.md:每条 `### N. 术语名 (English)` + 其后 `**一句话定义：** 定义` → {name, definition}。 */
function parseGlossaryTerms(md: string): GlossaryTerm[] {
  const terms: GlossaryTerm[] = []
  const lines = md.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const h = lines[i].match(/^###\s+\d+\.\s+(.+?)\s*$/)
    if (!h) continue
    // 去掉标题里的英文括号注释,取中文术语名(如「多头 / 做多 (Long)」→「多头 / 做多」)
    const name = h[1].replace(/\s*\([^)]*\)\s*$/, '').trim()
    // 向后找最近的「一句话定义」行
    let definition = ''
    for (let j = i + 1; j < Math.min(i + 8, lines.length); j++) {
      const d = lines[j].match(/\*\*一句话定义：\*\*\s*(.+?)\s*$/)
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
export function buildGlossaryTermSet() {
  const terms = parseGlossaryTerms(getGlossary())
  return {
    '@context': 'https://schema.org',
    '@type': 'DefinedTermSet',
    '@id': `${BASE}/academy/glossary#termset`,
    name: '点金训练营 · 交易名词词典',
    inLanguage: 'zh-CN',
    url: `${BASE}/academy/glossary`,
    hasDefinedTerm: terms.map((t) => ({
      '@type': 'DefinedTerm',
      name: t.name,
      description: t.definition,
      inDefinedTermSet: `${BASE}/academy/glossary#termset`,
    })),
  }
}
