/** 显示偏好 cookie 模块单测(刀1):容错 coerce + read/write 往返 + ★做T 默认关。 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  DEFAULT_DISPLAY_PREFS,
  coerceDisplayPrefs,
  readDisplayPrefs,
  writeDisplayPrefs,
} from './display-prefs'

function clearCookie() {
  document.cookie = 'display_prefs=; path=/; max-age=0'
}

beforeEach(clearCookie)
afterEach(clearCookie)

describe('coerceDisplayPrefs · 容错降级系统默认', () => {
  it('null / undefined → 系统默认', () => {
    expect(coerceDisplayPrefs(null)).toEqual(DEFAULT_DISPLAY_PREFS)
    expect(coerceDisplayPrefs(undefined)).toEqual(DEFAULT_DISPLAY_PREFS)
  })
  it('数组 / 字符串 / 数字 → 系统默认', () => {
    expect(coerceDisplayPrefs([])).toEqual(DEFAULT_DISPLAY_PREFS)
    expect(coerceDisplayPrefs('boom')).toEqual(DEFAULT_DISPLAY_PREFS)
    expect(coerceDisplayPrefs(42)).toEqual(DEFAULT_DISPLAY_PREFS)
  })
  it('空对象 → 系统默认(★做T 默认关)', () => {
    const p = coerceDisplayPrefs({})
    expect(p).toEqual(DEFAULT_DISPLAY_PREFS)
    expect(p.indicators.dott).toBe(false)
  })
  it('部分字段 → 缺失项填系统默认', () => {
    const p = coerceDisplayPrefs({ indicators: { boll: false }, period: '15m' })
    expect(p.indicators.boll).toBe(false) // 显式给的保留
    expect(p.indicators.chan).toBe(true) // 缺失填默认
    expect(p.indicators.dott).toBe(false)
    expect(p.period).toBe('15m')
  })
  it('字段类型错(非 bool / 非 string)→ 用默认填', () => {
    const p = coerceDisplayPrefs({ indicators: { boll: 'yes', macd: 1 }, period: 99 })
    expect(p.indicators.boll).toBe(true) // 'yes' 非 bool → 默认 true
    expect(p.indicators.macd).toBe(true)
    expect(p.period).toBe('1h') // 99 非 string → 默认
  })
})

describe('★做T 默认关', () => {
  it('系统默认 dott=false,boll/chan/macd=true', () => {
    expect(DEFAULT_DISPLAY_PREFS.indicators).toEqual({
      boll: true,
      chan: true,
      macd: true,
      dott: false,
    })
    expect(DEFAULT_DISPLAY_PREFS.period).toBe('1h')
  })
})

describe('readDisplayPrefs / writeDisplayPrefs · cookie 往返 + 容错', () => {
  it('无 cookie → 系统默认', () => {
    expect(readDisplayPrefs()).toEqual(DEFAULT_DISPLAY_PREFS)
  })
  it('坏 JSON cookie → 系统默认(不崩)', () => {
    document.cookie = 'display_prefs=%7Bnot-json; path=/'
    expect(readDisplayPrefs()).toEqual(DEFAULT_DISPLAY_PREFS)
  })
  it('write 后 read 往返一致', () => {
    const custom = {
      indicators: { boll: false, chan: true, macd: false, dott: true },
      period: '1d',
    }
    writeDisplayPrefs(custom)
    expect(readDisplayPrefs()).toEqual(custom)
  })
  it('write 不影响涨跌色 color_pref cookie', () => {
    document.cookie = 'color_pref=green-up; path=/'
    writeDisplayPrefs(DEFAULT_DISPLAY_PREFS)
    expect(document.cookie).toContain('color_pref=green-up') // 独立 cookie,不互踩
    expect(document.cookie).toContain('display_prefs=')
  })
})
