import { describe, it, expect } from 'vitest'

import { gridLevels, simulateGrid } from './grid-trading.calc'

describe('D20 网格交易口径', () => {
  it('网格价位等分', () => {
    expect(gridLevels(100, 110, 5)).toEqual([100, 102, 104, 106, 108, 110])
  })
  it('★震荡市来回穿格→实现价差收益>0', () => {
    const r = simulateGrid(100, 110, 5, [110, 104, 110, 104, 110])
    expect(r.realized).toBeGreaterThan(0)
    expect(r.sells).toBeGreaterThan(0)
  })
  it('★单边下跌→只买不卖、持仓堆积套牢', () => {
    const r = simulateGrid(100, 110, 5, [110, 108, 106, 104, 102, 100])
    expect(r.openLots).toBeGreaterThan(0)
    expect(r.sells).toBe(0)
  })
})
