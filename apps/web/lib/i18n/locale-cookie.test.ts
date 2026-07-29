import { beforeEach, describe, expect, it } from 'vitest'

import {
  getLocaleCookie,
  hasLocaleCookie,
  setLocaleCookie,
} from './locale-cookie'

describe('locale cookie', () => {
  beforeEach(() => {
    document.cookie = 'NEXT_LOCALE=; path=/; max-age=0'
  })

  it('defaults to Chinese without a valid cookie', () => {
    expect(hasLocaleCookie()).toBe(false)
    expect(getLocaleCookie()).toBe('zh')
  })

  it('persists both supported locales', () => {
    setLocaleCookie('en')
    expect(hasLocaleCookie()).toBe(true)
    expect(getLocaleCookie()).toBe('en')

    setLocaleCookie('zh')
    expect(getLocaleCookie()).toBe('zh')
  })
})
