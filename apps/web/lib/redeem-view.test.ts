/** 兑换码展示纯逻辑单测(兑换码刀2)。 */

import { describe, expect, it } from 'vitest'

import {
  joinCodes,
  periodLabel,
  redeemErrorText,
  redeemSuccessText,
  statusClass,
} from './redeem-view'

describe('redeemErrorText(三态 · 严格校验形状不误判)', () => {
  it('后端结构化 error → 对应中文文案', () => {
    expect(redeemErrorText({ error: 'not_found', message: 'x' })).toBe('兑换码无效')
    expect(redeemErrorText({ error: 'already_used' })).toBe('该兑换码已被使用')
    expect(redeemErrorText({ error: 'expired' })).toBe('兑换码已过期')
  })

  it('形状不符 → null(走通用文案,不误判)', () => {
    expect(redeemErrorText(null)).toBeNull()
    expect(redeemErrorText('HTTP 500')).toBeNull()
    expect(redeemErrorText({ error: 123 })).toBeNull()
    expect(redeemErrorText({ message: 'no error key' })).toBeNull()
    expect(redeemErrorText({ error: 'unknown_code' })).toBeNull() // 未知 error 值 → 通用
  })
})

describe('redeemSuccessText(按天数判档)', () => {
  it('365→年卡 / 90→季卡 / 30→月卡', () => {
    expect(redeemSuccessText({ plan: 'pro', days_added: 365, expires_at: null })).toBe('已兑换年卡 · Pro +365 天')
    expect(redeemSuccessText({ plan: 'pro', days_added: 90, expires_at: null })).toBe('已兑换季卡 · Pro +90 天')
    expect(redeemSuccessText({ plan: 'pro', days_added: 30, expires_at: null })).toBe('已兑换月卡 · Pro +30 天')
  })
})

describe('joinCodes(复制全部 · 换行分隔)', () => {
  it('多码换行拼接', () => {
    expect(joinCodes(['AAA', 'BBB', 'CCC'])).toBe('AAA\nBBB\nCCC')
    expect(joinCodes(['ONLY'])).toBe('ONLY')
  })
})

describe('periodLabel / statusClass', () => {
  it('周期中文', () => {
    expect(periodLabel('month')).toBe('月卡')
    expect(periodLabel('year')).toBe('年卡')
    expect(periodLabel('weird')).toBe('weird')
  })
  it('未用墨绿 · 已用/过期灰', () => {
    expect(statusClass('unused')).toContain('text-down')
    expect(statusClass('redeemed')).toContain('muted')
    expect(statusClass('expired')).toContain('muted')
  })
})
