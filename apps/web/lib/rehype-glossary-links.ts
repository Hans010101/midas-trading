import { visit } from 'unist-util-visit'
import type { Root, Element, Text } from 'hast'

import type { AliasEntry } from './glossary-terms'

export interface MatchSegment {
  type: 'text' | 'link'
  value: string
  id?: string
}

/**
 * 核心匹配(纯函数,便于单测):
 * - 最长优先(sortedAliases 已按别名长度降序)
 * - 排除集(excludeSet)跳过
 * - 首次 only:alreadyLinked 按 id 去重,跨整篇所有 text 节点共享同一 set
 */
export function matchTermsInText(
  text: string,
  sortedAliases: AliasEntry[],
  excludeSet: Set<string>,
  alreadyLinked: Set<string>,
): MatchSegment[] {
  const segs: MatchSegment[] = []
  let buf = ''
  let i = 0
  while (i < text.length) {
    let hit: AliasEntry | null = null
    for (const a of sortedAliases) {
      if (excludeSet.has(a.alias)) continue
      if (alreadyLinked.has(a.id)) continue
      if (text.startsWith(a.alias, i)) {
        hit = a
        break
      }
    }
    if (hit) {
      if (buf) {
        segs.push({ type: 'text', value: buf })
        buf = ''
      }
      segs.push({ type: 'link', value: hit.alias, id: hit.id })
      alreadyLinked.add(hit.id)
      i += hit.alias.length
    } else {
      buf += text[i]
      i += 1
    }
  }
  if (buf) segs.push({ type: 'text', value: buf })
  return segs
}

// 这些标签内的 text 不挂锚:已有链接、行内/块代码、标题
const SKIP_TAGS = new Set(['a', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

export interface RehypeGlossaryOptions {
  sortedAliases: AliasEntry[]
  exclude?: string[]
}

/** rehype 插件:扫 HAST text 节点,首次出现的术语包成 <a href="/academy/glossary#id"> */
export function rehypeGlossaryLinks(options: RehypeGlossaryOptions) {
  const excludeSet = new Set(options.exclude ?? [])
  return (tree: Root) => {
    const alreadyLinked = new Set<string>()
    visit(tree, 'text', (node: Text, index, parent) => {
      if (parent == null || index == null) return
      if (parent.type === 'element' && SKIP_TAGS.has((parent as Element).tagName)) return
      const segs = matchTermsInText(node.value, options.sortedAliases, excludeSet, alreadyLinked)
      if (segs.length === 1 && segs[0].type === 'text') return
      const replacement: Array<Text | Element> = segs.map((s) =>
        s.type === 'text'
          ? ({ type: 'text', value: s.value } as Text)
          : ({
              type: 'element',
              tagName: 'a',
              properties: { href: `/academy/glossary#${s.id}` },
              children: [{ type: 'text', value: s.value } as Text],
            } as Element),
      )
      ;(parent as Element).children.splice(index, 1, ...replacement)
      return index + replacement.length
    })
  }
}
