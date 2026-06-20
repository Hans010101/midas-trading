import { describe, it, expect } from 'vitest'

import {
  ACADEMY_INTERACTIVES,
  ALL_KEYS,
  IMPLEMENTED_KEYS,
  getInteractives,
} from './interactives'

describe('D 系列 interactives 映射', () => {
  it('getInteractives:命中返回 key 列表、未命中返回 null', () => {
    expect(getInteractives('E4')).toEqual(['liquidation'])
    expect(getInteractives('C7')).toEqual(['chan-pivot'])
    expect(getInteractives('A2')).toEqual(['kline'])
    expect(getInteractives('__nope__')).toBeNull()
  })

  it('每篇映射的数组非空', () => {
    for (const [slug, keys] of Object.entries(ACADEMY_INTERACTIVES)) {
      expect(keys.length, slug).toBeGreaterThan(0)
    }
  })

  it('映射里出现的每个 key 都属于已知 key 全集(防拼写错误)', () => {
    const known = new Set(ALL_KEYS)
    for (const keys of Object.values(ACADEMY_INTERACTIVES)) {
      for (const k of keys) expect(known.has(k), k).toBe(true)
    }
  })

  it('★只能映射到【已实现】的组件(防把文章挂到未建组件上)', () => {
    const impl = new Set<string>(IMPLEMENTED_KEYS)
    for (const keys of Object.values(ACADEMY_INTERACTIVES)) {
      for (const k of keys) expect(impl.has(k), `${k} 尚未实现却被映射`).toBe(true)
    }
  })

  it('ALL_KEYS 无重复', () => {
    expect(new Set(ALL_KEYS).size).toBe(ALL_KEYS.length)
  })
})
