import { beforeEach, describe, expect, it } from 'vitest'

import { hasSeenAcademyPromo, markAcademyPromoSeen } from './academy-popup'

describe('academy-popup 首访 cookie 判定', () => {
  beforeEach(() => {
    // 清掉 cookie(jsdom)
    document.cookie = 'academy_promo_seen=; path=/; max-age=0'
  })

  it('初始未看过 → false(应弹)', () => {
    expect(hasSeenAcademyPromo()).toBe(false)
  })

  it('★标记后 → true(关闭后不再弹)+ cookie 写入 =1', () => {
    markAcademyPromoSeen()
    expect(hasSeenAcademyPromo()).toBe(true)
    expect(document.cookie).toContain('academy_promo_seen=1')
  })

  it('不误判其它 cookie(子串安全)', () => {
    document.cookie = 'other_academy_promo_seen_x=1; path=/'
    expect(hasSeenAcademyPromo()).toBe(false)
  })
})
