// 从 glossary.md 的 `### N. 术语 (English)` 标题派生 术语别名 → 锚点 id。
// id 规则必须与词典端 article-renderer.tsx 的 h3 渲染一致(glossaryAnchorId),才对得上 #锚点。

export interface TermEntry {
  aliases: string[]
  id: string
}
export interface AliasEntry {
  alias: string
  id: string
}

/** 与词典端 h3 同一规则:剥离结尾英文/中文括注、去所有空白(/ + 保留) */
export function glossaryAnchorId(headingText: string): string | null {
  const m = headingText.match(/^\s*\d+\.\s*(.+)$/s)
  if (!m) return null
  let term = m[1].trim()
  term = term.replace(/[（(][^（()）]*[)）]\s*$/, '').trim()
  if (!term) return null
  return term.replace(/\s+/g, '')
}

/** 解析 glossary.md → 术语条目(别名 + id);别名按 / 拆中文叫法,英文括注剥离 */
export function parseGlossaryTerms(md: string): TermEntry[] {
  const out: TermEntry[] = []
  for (const line of md.split('\n')) {
    const m = line.match(/^###\s+(\d+\.\s*.+?)\s*$/)
    if (!m) continue
    const headingText = m[1]
    const id = glossaryAnchorId(headingText)
    if (!id) continue
    const tm = headingText.match(/^\s*\d+\.\s*(.+)$/)
    if (!tm) continue
    const term = tm[1].trim().replace(/[（(][^（()）]*[)）]\s*$/, '').trim()
    const aliases = term.split('/').map((s) => s.trim()).filter(Boolean)
    if (aliases.length === 0) continue
    out.push({ aliases, id })
  }
  return out
}

/** 别名扁平化 + 按别名长度降序(最长优先匹配);别名去重(同名取首个) */
export function buildSortedAliases(terms: TermEntry[]): AliasEntry[] {
  const seen = new Set<string>()
  const list: AliasEntry[] = []
  for (const t of terms) {
    for (const alias of t.aliases) {
      if (seen.has(alias)) continue
      seen.add(alias)
      list.push({ alias, id: t.id })
    }
  }
  return list.sort((a, b) => b.alias.length - a.alias.length)
}

/**
 * A+C 防误匹配 · 默认排除的高危短词(极易作普通词出现)。
 * 取自 Code 核出的 23 个 ≤2 字术语里、作普通词概率最高的几个。Hans 可增减。
 * 其余 ≤2 字术语(杠杆/止损/止盈/中枢/背驰 等基本只在交易语境)默认仍挂。
 */
export const DEFAULT_EXCLUDE_TERMS = ['笔', '趋势', '实体', '缺口', '仓位']
