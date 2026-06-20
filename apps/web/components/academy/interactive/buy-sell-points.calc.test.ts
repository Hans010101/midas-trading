import { describe, it, expect } from 'vitest'

import { classifyBuy2, classifyBuy3, classifySell2, classifySell3 } from './buy-sell-points.calc'

// ★★ 买卖点是结构术语、非买卖指令;本测试仅验结构分类逻辑,不含交易语义
describe('D17 买卖点口径(结构分类,非交易指令)', () => {
  it('★二买=回调不破前低', () => {
    expect(classifyBuy2(105, 100)).toBe('buy2')
    expect(classifyBuy2(95, 100)).toBe('none')
  })
  it('★三买=回踩不破中枢上沿 ZG', () => {
    expect(classifyBuy3(105, 100)).toBe('buy3')
    expect(classifyBuy3(95, 100)).toBe('none')
  })
  it('卖点对称(二卖不破前高、三卖不破 ZD)', () => {
    expect(classifySell2(95, 100)).toBe('sell2')
    expect(classifySell3(95, 100)).toBe('sell3')
  })
})
