/** 词典锚点 id 生成 · 规则钉死(★序号无关 = 防漂移;文章端链接与词典端 id 必须同规则)。 */

import { describe, expect, it } from 'vitest'

import { glossaryAnchorId } from './academy-anchor'

describe('glossaryAnchorId', () => {
  it('去序号 + 去英文括注', () => {
    expect(glossaryAnchorId('58. 中枢')).toBe('中枢')
    expect(glossaryAnchorId('59. 背驰')).toBe('背驰')
    expect(glossaryAnchorId('3. 杠杆 (Leverage)')).toBe('杠杆')
    expect(glossaryAnchorId('15. 资金费率 (Funding Rate)')).toBe('资金费率')
  })

  it('去中文括注', () => {
    expect(glossaryAnchorId('40. RSI（相对强弱指标）')).toBe('RSI')
    expect(glossaryAnchorId('30. K线（蜡烛图）')).toBe('K线')
    expect(glossaryAnchorId('55. 分型（顶分型 / 底分型）')).toBe('分型')
    expect(glossaryAnchorId('60. 缠论买卖点（三类买卖点）')).toBe('缠论买卖点')
  })

  it('多别名(斜杠)去空白保留斜杠', () => {
    expect(glossaryAnchorId('1. 多头 / 做多 (Long)')).toBe('多头/做多')
    expect(glossaryAnchorId('37. 金叉 / 死叉')).toBe('金叉/死叉')
    expect(glossaryAnchorId('22. T+0 / T+1（交易结算周期）')).toBe('T+0/T+1')
  })

  it('纯英文词条 / 单字词条', () => {
    expect(glossaryAnchorId('38. MACD')).toBe('MACD')
    expect(glossaryAnchorId('56. 笔')).toBe('笔')
    expect(glossaryAnchorId('57. 线段')).toBe('线段')
  })

  it('★序号无关:换序号 id 不变(防词典增删导致锚点断)', () => {
    expect(glossaryAnchorId('58. 中枢')).toBe(glossaryAnchorId('99. 中枢'))
    expect(glossaryAnchorId('1. 中枢')).toBe('中枢')
  })

  it('非词条格式(普通文章 h3)→ null', () => {
    expect(glossaryAnchorId('暖金小标题')).toBeNull()
    expect(glossaryAnchorId('一、概念引入')).toBeNull()
    expect(glossaryAnchorId('')).toBeNull()
  })
})
