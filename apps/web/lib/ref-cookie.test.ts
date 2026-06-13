/** ref 归因 cookie 纯函数单测(Phase 1.5 刀B)。 */

import { describe, expect, it } from 'vitest'

import { buildRefCookie, normalizeRef, readRefFromCookieString, REF_COOKIE } from './ref-cookie'

describe('normalizeRef', () => {
  it('trim + 大写', () => {
    expect(normalizeRef('  abc123  ')).toBe('ABC123')
    expect(normalizeRef('XYZ')).toBe('XYZ')
  })

  it('空 / null / 超长(>12)→ null', () => {
    expect(normalizeRef(null)).toBeNull()
    expect(normalizeRef('')).toBeNull()
    expect(normalizeRef('   ')).toBeNull()
    expect(normalizeRef('A'.repeat(13))).toBeNull()
  })
})

describe('buildRefCookie / readRefFromCookieString', () => {
  it('写入串含 key + path + max-age + samesite', () => {
    const c = buildRefCookie('ABC123')
    expect(c).toContain(`${REF_COOKIE}=ABC123`)
    expect(c).toContain('path=/')
    expect(c).toContain('max-age=2592000') // 30d
    expect(c).toContain('samesite=lax')
  })

  it('从 cookie 串解析(含其他 cookie 干扰)', () => {
    expect(readRefFromCookieString('foo=1; midas_ref=ABC123; bar=2')).toBe('ABC123')
    expect(readRefFromCookieString('midas_ref=xyz')).toBe('XYZ') // 解析后 normalize
  })

  it('缺失 / null → null', () => {
    expect(readRefFromCookieString(null)).toBeNull()
    expect(readRefFromCookieString('foo=1; bar=2')).toBeNull()
  })
})
