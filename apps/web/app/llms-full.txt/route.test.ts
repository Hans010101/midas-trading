import { describe, expect, it } from 'vitest'

import { getAcademyArticles } from '@/content/academy/localized-catalog'
import { getArticleBySlug } from '@/lib/academy'

import { GET } from './route'

describe('llms-full.txt', () => {
  it('publishes a readable Markdown title for every lesson', () => {
    for (const locale of ['zh', 'en'] as const) {
      for (const { slug } of getAcademyArticles(locale)) {
        expect(getArticleBySlug(slug, locale)?.trimStart(), `${locale}/${slug}`).toMatch(/^# [^\n]+/)
      }
    }
  })

  it('contains discoverable Chinese and English full-text editions', async () => {
    const body = await GET().text()

    expect(body).toContain('第一部分 · 交易名词词典')
    expect(body).toContain('English Trading Glossary')
    expect(body).toContain('https://midastrade.asia/academy/article/')
    expect(body).toContain('https://midastrade.asia/en/academy/article/')
    expect(body).toContain('One-sentence definition:')
  })
})
