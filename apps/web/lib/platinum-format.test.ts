import { describe, expect, it } from 'vitest'

import {
  holdLabel,
  pnlTone,
  scoreTone,
  sideLabel,
  sideTone,
} from '@/lib/platinum-format'

describe('platinum-format', () => {
  it('pnlTone 盈红亏绿中性灰', () => {
    expect(pnlTone(1)).toBe('text-rose-600') // 盈利红
    expect(pnlTone(-1)).toBe('text-emerald-700') // 亏损绿
    expect(pnlTone(0)).toBe('text-muted-foreground')
  })

  it('sideTone 做多绿做空红(★西式·不随涨跌偏好翻转)', () => {
    expect(sideTone('long')).toBe('text-emerald-700') // 做多绿
    expect(sideTone('short')).toBe('text-rose-600') // 做空红
  })

  it('sideLabel long→做多 其它→做空', () => {
    expect(sideLabel('long')).toBe('做多')
    expect(sideLabel('short')).toBe('做空')
  })

  it('scoreTone 正绿负红零金', () => {
    expect(scoreTone(3)).toBe('text-emerald-700')
    expect(scoreTone(-3)).toBe('text-rose-600')
    expect(scoreTone(0)).toBe('text-gold')
  })

  it('holdLabel 秒→Xh Ym', () => {
    expect(holdLabel(3661)).toBe('1h1m')
    expect(holdLabel(0)).toBe('0h0m')
    expect(holdLabel(7200)).toBe('2h0m')
  })
})
