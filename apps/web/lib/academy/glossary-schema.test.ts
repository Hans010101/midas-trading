import { describe, expect, it } from 'vitest'

import { buildGlossaryTermSet } from './glossary-schema'

describe('buildGlossaryTermSet', () => {
  it('builds separate populated Chinese and English term sets', () => {
    const zh = buildGlossaryTermSet()
    const en = buildGlossaryTermSet('en')

    expect(zh.inLanguage).toBe('zh-CN')
    expect(en.inLanguage).toBe('en')
    expect(en.url).toBe('https://midastrade.asia/en/academy/glossary')
    expect(zh.hasDefinedTerm.length).toBeGreaterThan(80)
    expect(en.hasDefinedTerm.length).toBeGreaterThan(80)
    expect(en.hasDefinedTerm[0]?.description).toBeTruthy()
  })
})
