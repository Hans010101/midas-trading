/** 到账感知文案 + 一次性 cookie 纯函数单测(Phase 1.5 刀B)。 */

import { describe, expect, it } from 'vitest'

import {
  buildRewardCookieValue,
  parseRewardCookie,
  rewardToastMessage,
} from './reward-toast'

describe('rewardToastMessage(诚实文案 · 天数如实)', () => {
  it('两者同时 → 合并(7 试用 + 15 邀请)', () => {
    expect(rewardToastMessage(true, true)).toBe('已获赠 7 天 Pro 试用 · 邀请奖励 +15 天已到账')
  })
  it('仅试用 / 仅邀请', () => {
    expect(rewardToastMessage(true, false)).toBe('已获赠 7 天 Pro 试用')
    expect(rewardToastMessage(false, true)).toBe('邀请奖励已到账 · Pro +15 天')
  })
  it('都没有 → null(不弹 toast)', () => {
    expect(rewardToastMessage(false, false)).toBeNull()
  })
})

describe('reward cookie 编解码', () => {
  it('build:按 flag 组合 · 都无 → null', () => {
    expect(buildRewardCookieValue(true, true)).toBe('trial,invite')
    expect(buildRewardCookieValue(true, false)).toBe('trial')
    expect(buildRewardCookieValue(false, true)).toBe('invite')
    expect(buildRewardCookieValue(false, false)).toBeNull()
  })

  it('parse:round-trip', () => {
    expect(parseRewardCookie('trial,invite')).toEqual({ trial: true, invite: true })
    expect(parseRewardCookie('trial')).toEqual({ trial: true, invite: false })
    expect(parseRewardCookie('invite')).toEqual({ trial: false, invite: true })
    expect(parseRewardCookie(null)).toEqual({ trial: false, invite: false })
    expect(parseRewardCookie('')).toEqual({ trial: false, invite: false })
  })
})
