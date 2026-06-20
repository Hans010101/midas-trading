import { describe, it, expect } from 'vitest'

import { classifyMarket } from './trend-range.calc'

describe('D19 趋势与震荡口径', () => {
  it('★高低点都抬高=上升趋势', () => {
    expect(classifyMarket([10, 12, 14], [8, 9, 11])).toBe('uptrend')
  })
  it('★高低点都降低=下降趋势', () => {
    expect(classifyMarket([14, 12, 10], [11, 9, 8])).toBe('downtrend')
  })
  it('★高低点无序=震荡', () => {
    expect(classifyMarket([10, 12, 11], [8, 9, 8])).toBe('range')
  })
})
