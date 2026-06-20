import { describe, it, expect } from 'vitest'

import { detectFractals, buildBi, type Fractal } from './fractal-bi.calc'

describe('D15 分型与笔口径', () => {
  it('★顶分型=中间K高低点都最高', () => {
    expect(detectFractals([{ high: 5, low: 1 }, { high: 9, low: 4 }, { high: 6, low: 2 }])).toEqual([{ index: 1, type: 'top' }])
  })
  it('★底分型=中间K高低点都最低', () => {
    expect(detectFractals([{ high: 9, low: 5 }, { high: 6, low: 1 }, { high: 8, low: 4 }])).toEqual([{ index: 1, type: 'bottom' }])
  })
  it('★笔=顶底分型交替连接(底→顶上升、顶→底下降)', () => {
    const fr: Fractal[] = [{ index: 1, type: 'bottom' }, { index: 4, type: 'top' }, { index: 7, type: 'bottom' }]
    expect(buildBi(fr)).toEqual([
      { fromIndex: 1, toIndex: 4, direction: 'up' },
      { fromIndex: 4, toIndex: 7, direction: 'down' },
    ])
  })
})
