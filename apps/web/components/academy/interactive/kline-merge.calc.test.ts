import { describe, it, expect } from 'vitest'

import { hasContainment, mergeKline } from './kline-merge.calc'

describe('D14 K线合并口径', () => {
  it('包含关系判定', () => {
    expect(hasContainment({ high: 10, low: 4 }, { high: 8, low: 5 })).toBe(true) // 前包后
    expect(hasContainment({ high: 10, low: 4 }, { high: 12, low: 6 })).toBe(false) // 交叉不含
  })
  it('★向上处理取「高高」(高点低点都取高者)', () => {
    expect(mergeKline({ high: 10, low: 4 }, { high: 8, low: 5 }, 'up')).toEqual({ high: 10, low: 5 })
  })
  it('★向下处理取「低低」(高点低点都取低者)', () => {
    expect(mergeKline({ high: 10, low: 4 }, { high: 8, low: 5 }, 'down')).toEqual({ high: 8, low: 4 })
  })
})
