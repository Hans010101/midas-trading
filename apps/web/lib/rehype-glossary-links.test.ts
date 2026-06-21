import { describe, it, expect } from 'vitest'
import { unified } from 'unified'
import rehypeParse from 'rehype-parse'
import rehypeStringify from 'rehype-stringify'

import { parseGlossaryTerms, buildSortedAliases } from './glossary-terms'
import { rehypeGlossaryLinks, matchTermsInText } from './rehype-glossary-links'

// 仿真 glossary.md(含 / 中文别名、英文括注、长词 vs 短词、高危短词)
const SAMPLE = `
### 1. 多头 / 做多 (Long)
做多就是买入。
### 3. 杠杆 (Leverage)
杠杆放大收益与风险。
### 14. 资金费率 (Funding Rate)
资金费率每 8 小时结算。
### 50. 费率
单独的费率词条。
### 60. 笔 (Bi)
缠论里的一笔。
`
const terms = parseGlossaryTerms(SAMPLE)
const sorted = buildSortedAliases(terms)

function render(html: string, exclude: string[] = []): string {
  return unified()
    .use(rehypeParse, { fragment: true })
    .use(rehypeGlossaryLinks, { sortedAliases: sorted, exclude })
    .use(rehypeStringify)
    .processSync(html)
    .toString()
}

describe('parseGlossaryTerms', () => {
  it('★标题→别名→id:/ 拆中文别名、英文括注剥离、id 去空白', () => {
    const long = terms.find((t) => t.id === '多头/做多')
    expect(long).toBeTruthy()
    expect(long!.aliases).toEqual(['多头', '做多'])
    expect(terms.find((t) => t.id === '杠杆')!.aliases).toEqual(['杠杆'])
    expect(terms.find((t) => t.id === '资金费率')).toBeTruthy()
  })
})

describe('rehype 挂锚(真实 rehype 管线)', () => {
  it('术语首次出现包成 /academy/glossary# 链接', () => {
    expect(render('<p>杠杆放大收益</p>')).toContain('<a href="/academy/glossary#杠杆">杠杆</a>')
  })
  it('★最长优先:资金费率 整体挂,不被费率拆碎', () => {
    const out = render('<p>资金费率很关键</p>')
    expect(out).toContain('href="/academy/glossary#资金费率">资金费率</a>')
    expect(out).not.toContain('#费率">资金')
  })
  it('★中文别名:做多 链到 多头/做多', () => {
    expect(render('<p>做多就是买入</p>')).toContain('href="/academy/glossary#多头/做多">做多</a>')
  })
  it('★首次 only:杠杆出现两次只挂第一次', () => {
    const out = render('<p>杠杆和杠杆</p>')
    expect(out.match(/href="\/academy\/glossary#杠杆"/g)!.length).toBe(1)
  })
  it('★A+C 排除集:笔 不挂', () => {
    expect(render('<p>缠论里的一笔</p>', ['笔'])).not.toContain('#笔"')
  })
  it('★跳过代码块:code 内术语不挂', () => {
    expect(render('<p>看 <code>杠杆</code> 字段</p>')).not.toContain('#杠杆"')
  })
  it('★跳过已有链接:a 内不嵌套', () => {
    const out = render('<p><a href="/x">杠杆</a></p>')
    expect(out.match(/<a /g)!.length).toBe(1)
  })
  it('★跳过标题:h3 内术语不挂', () => {
    expect(render('<h3>杠杆原理</h3>')).not.toContain('#杠杆"')
  })
  it('粗体内术语正常挂', () => {
    expect(render('<p><strong>杠杆</strong></p>')).toContain('href="/academy/glossary#杠杆"')
  })
})

describe('matchTermsInText 纯函数', () => {
  it('★首次 only 跨节点共享 alreadyLinked', () => {
    const already = new Set<string>()
    const ex = new Set<string>()
    const s1 = matchTermsInText('杠杆', sorted, ex, already)
    const s2 = matchTermsInText('杠杆', sorted, ex, already)
    expect(s1.some((x) => x.type === 'link')).toBe(true)
    expect(s2.some((x) => x.type === 'link')).toBe(false)
  })
})
