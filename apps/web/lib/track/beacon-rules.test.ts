import { describe, expect, it } from 'vitest'

import { classifyCrawler, extractRefHost, isPrefetchRequest, normalizeHost } from './beacon-rules'

describe('normalizeHost', () => {
  it('小写 · 去端口 · 去 www', () => {
    expect(normalizeHost('WWW.Midastrade.Asia')).toBe('midastrade.asia')
    expect(normalizeHost('localhost:3000')).toBe('localhost')
    expect(normalizeHost('midastrade.asia:443')).toBe('midastrade.asia')
  })
})

describe('extractRefHost · Bug A 自指判断(selfHost 来自 Host 头)', () => {
  const SELF = 'midastrade.asia'

  it('★站内跳转(同域 referer)→ null(不记来源)', () => {
    expect(extractRefHost('https://midastrade.asia/cn-market', SELF)).toBeNull()
    expect(extractRefHost('https://midastrade.asia/academy/article/foo?x=1', SELF)).toBeNull()
  })

  it('★www/apex 不对称也算自指 → null(两侧都归一去 www)', () => {
    expect(extractRefHost('https://www.midastrade.asia/foo', SELF)).toBeNull()
    expect(extractRefHost('https://midastrade.asia/foo', 'www.midastrade.asia')).toBeNull()
  })

  it('★本地 dev:selfHost 带端口也能识别自指', () => {
    expect(extractRefHost('http://localhost:3000/workbench', 'localhost:3000')).toBeNull()
  })

  it('真实外部来源 → 返回归一后的 host', () => {
    expect(extractRefHost('https://www.google.com/search?q=x', SELF)).toBe('google.com')
    expect(extractRefHost('https://t.co/abc', SELF)).toBe('t.co')
    expect(extractRefHost('https://chat.openai.com/', SELF)).toBe('chat.openai.com')
  })

  it('无 referer / 非法 referer / selfHost 缺失 → 稳健', () => {
    expect(extractRefHost(null, SELF)).toBeNull()
    expect(extractRefHost('not-a-url', SELF)).toBeNull()
    // selfHost 缺失时无法判自指,退化为记录外部 host(后端 classify_source 自有域兜底)
    expect(extractRefHost('https://midastrade.asia/foo', null)).toBe('midastrade.asia')
  })
})

describe('isPrefetchRequest · Bug B 预取排除(★对照:预取不计 / 真导航计)', () => {
  it('★Next auto 预取(next-router-prefetch:1)→ true(不计 PV)', () => {
    const h = new Headers({ rsc: '1', 'next-router-prefetch': '1' })
    expect(isPrefetchRequest(h)).toBe(true)
  })

  it('★分段/PPR 预取(next-router-segment-prefetch)→ true', () => {
    const h = new Headers({ 'next-router-segment-prefetch': '/cn-market' })
    expect(isPrefetchRequest(h)).toBe(true)
  })

  it('★浏览器推测加载(sec-purpose: prefetch)→ true', () => {
    expect(isPrefetchRequest(new Headers({ 'sec-purpose': 'prefetch' }))).toBe(true)
    expect(isPrefetchRequest(new Headers({ 'sec-purpose': 'prefetch;prerender' }))).toBe(true)
  })

  it('★真软导航(点击 · rsc 但无预取头)→ false(照常计 PV)', () => {
    const h = new Headers({ rsc: '1', 'next-router-state-tree': '["",{}]' })
    expect(isPrefetchRequest(h)).toBe(false)
  })

  it('★硬导航(全页文档 · 无任何 Next 头)→ false(照常计 PV)', () => {
    const h = new Headers({ 'user-agent': 'Mozilla/5.0', accept: 'text/html' })
    expect(isPrefetchRequest(h)).toBe(false)
  })
})

describe('classifyCrawler · 爬虫仍独立计数(不受 Bug B 影响)', () => {
  it('AI/搜索爬虫命中桶名', () => {
    expect(classifyCrawler('Mozilla/5.0 (compatible; GPTBot/1.2)')).toBe('GPTBot')
    expect(classifyCrawler('Mozilla/5.0 (compatible; Googlebot/2.1)')).toBe('search:Googlebot')
    expect(classifyCrawler('Mozilla/5.0 (compatible; ClaudeBot/1.0)')).toBe('ClaudeBot')
  })
  it('真人浏览器 UA → null(不计爬虫)', () => {
    expect(classifyCrawler('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120')).toBeNull()
  })
})
