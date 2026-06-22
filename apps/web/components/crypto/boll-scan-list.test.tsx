/** 布林做T列表(A-2)红线单测:结构倾向配色复用涨跌色偏好(不写死红绿)+ %B 位置标注。 */

import { describe, expect, it } from 'vitest'

import { biasTone, pctbZone } from './boll-scan-list'

describe('biasTone · 结构倾向配色复用涨跌色偏好', () => {
  it('偏多 → text-up(= var(--color-up) · 随用户涨跌色偏好翻转,非写死红)', () => {
    expect(biasTone('偏多')).toBe('text-up')
  })
  it('偏空 → text-down(= var(--color-down) · 非写死绿)', () => {
    expect(biasTone('偏空')).toBe('text-down')
  })
  it('中性 → 中性灰(text-muted-foreground)', () => {
    expect(biasTone('中性')).toBe('text-muted-foreground')
  })
  it('★绝不返回写死红绿(无 text-red / text-green / 十六进制)', () => {
    for (const b of ['偏多', '偏空', '中性', '其他']) {
      const cls = biasTone(b)
      expect(cls).not.toMatch(/red|green|#|DC143C|0F6E5F/i)
    }
  })
})

describe('pctbZone · %B 位置标注(对齐后端阈值)', () => {
  it('>0.8 近上轨', () => expect(pctbZone(0.85)).toBe('近上轨'))
  it('<0.2 近下轨', () => expect(pctbZone(0.12)).toBe('近下轨'))
  it('0.4~0.6 近中轨', () => expect(pctbZone(0.5)).toBe('近中轨'))
  it('其余 中间', () => expect(pctbZone(0.3)).toBe('中间'))
})
