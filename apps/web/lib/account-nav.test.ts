/** 用户中心导航高亮纯函数单测(重组刀1)。 */

import { describe, expect, it } from 'vitest'

import { ACCOUNT_NAV_ITEMS, isActiveNavItem, normalizePositionsTab } from './account-nav'

const byHref = (href: string) => ACCOUNT_NAV_ITEMS.find((i) => i.href === href)!

describe('isActiveNavItem', () => {
  it('/account 精确匹配:子路由不误亮「资产总览」', () => {
    expect(isActiveNavItem('/account', byHref('/account'))).toBe(true)
    expect(isActiveNavItem('/account/positions', byHref('/account'))).toBe(false)
  })

  it('子模块前缀匹配各自高亮', () => {
    expect(isActiveNavItem('/account/positions', byHref('/account/positions'))).toBe(true)
    expect(isActiveNavItem('/account/alerts', byHref('/account/alerts'))).toBe(true)
    expect(isActiveNavItem('/account/profile', byHref('/account/profile'))).toBe(true)
    expect(isActiveNavItem('/account/alerts', byHref('/account/positions'))).toBe(false)
  })

  it('pathname null → 不高亮', () => {
    expect(isActiveNavItem(null, byHref('/account'))).toBe(false)
  })
})

describe('normalizePositionsTab(模块② URL tab 归一 · 刀3)', () => {
  it('四合法值原样通过', () => {
    expect(normalizePositionsTab('positions')).toBe('positions')
    expect(normalizePositionsTab('history')).toBe('history')
    expect(normalizePositionsTab('orders')).toBe('orders')
    expect(normalizePositionsTab('conditional')).toBe('conditional')
  })

  it('非法/缺省 → 默认 positions', () => {
    expect(normalizePositionsTab(null)).toBe('positions')
    expect(normalizePositionsTab('')).toBe('positions')
    expect(normalizePositionsTab('hack')).toBe('positions')
  })
})
