import { describe, it, expect } from 'vitest'

import { movingAverage, detectMaCrosses } from './moving-average.calc'

describe('D9 均线/金叉死叉口径', () => {
  it('MA(N) = 最近 N 根收盘价算术平均，不足 N 根为 null', () => {
    expect(movingAverage([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4])
  })

  it('★均线金叉 = 短期【上穿】长期（方向钉死）', () => {
    const short = [1, 2, 5, 6]
    const long = [3, 3, 3, 3]
    expect(detectMaCrosses(short, long)).toEqual([{ index: 2, type: 'golden' }])
  })

  it('★均线死叉 = 短期【下穿】长期', () => {
    const short = [5, 4, 1]
    const long = [3, 3, 3]
    expect(detectMaCrosses(short, long)).toEqual([{ index: 2, type: 'death' }])
  })

  it('长期线上穿短期 → 从短期视角是死叉，绝不误判成金叉', () => {
    const short = [3, 3, 3]
    const long = [1, 2, 5]
    const crosses = detectMaCrosses(short, long)
    expect(crosses).toEqual([{ index: 2, type: 'death' }])
    expect(crosses.some((c) => c.type === 'golden')).toBe(false)
  })

  it('不足 N 根（null）位置不产生交叉', () => {
    const short = [null, 2, 5]
    const long = [null, 3, 3]
    expect(detectMaCrosses(short, long)).toEqual([{ index: 2, type: 'golden' }])
  })
})
