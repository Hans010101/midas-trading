import { describe, it, expect } from 'vitest'

import { detectDivergence } from './divergence.calc'

describe('D16 背驰口径(力度比较,参考非反转)', () => {
  it('★价格新高但力度减弱=顶背驰', () => {
    expect(detectDivergence(100, 50, 110, 30, 'high')).toBe('top')
  })
  it('价格新高且力度增强=不背驰', () => {
    expect(detectDivergence(100, 50, 110, 70, 'high')).toBe('none')
  })
  it('★价格新低但力度减弱=底背驰', () => {
    expect(detectDivergence(100, -50, 90, -30, 'low')).toBe('bottom')
  })
})
