/** 额度展示纯逻辑单测(会员刀2)· 如实展示红线钉死。 */

import { describe, expect, it } from 'vitest'

import type { QuotaMe } from '@/lib/api/quota'
import {
  EXHAUSTED_TEXT,
  isExhausted,
  parseQuotaDetail,
  planLabel,
  quotaErrorMessage,
  quotaHintText,
  quotaItemFor,
  quotaRemaining,
} from './quota-view'

const me: QuotaMe = {
  plan: 'free',
  plan_expires_at: null,
  items: [
    { feature: 'diagnose', limit: 20, used: 3 },
    { feature: 'backtest', limit: 10, used: 10 },
  ],
  reset_at: '2026-06-14T00:00:00+08:00',
}

describe('剩余/耗尽(🔴 如实:剩几次是几次)', () => {
  it('quotaRemaining = limit - used · 超扣兜 0 不显负数', () => {
    expect(quotaRemaining({ feature: 'diagnose', limit: 20, used: 3 })).toBe(17)
    expect(quotaRemaining({ feature: 'diagnose', limit: 20, used: 23 })).toBe(0)
  })

  it('isExhausted:used >= limit', () => {
    expect(isExhausted({ feature: 'backtest', limit: 10, used: 10 })).toBe(true)
    expect(isExhausted({ feature: 'backtest', limit: 10, used: 9 })).toBe(false)
  })

  it('quotaHintText 文案口径「今日剩 N/20 次」', () => {
    expect(quotaHintText({ feature: 'diagnose', limit: 20, used: 3 })).toBe('今日剩 17/20 次')
  })

  it('耗尽文案含重置口径(UTC+8)', () => {
    expect(EXHAUSTED_TEXT).toContain('明日 0 点重置')
    expect(EXHAUSTED_TEXT).toContain('UTC+8')
  })

  it('quotaItemFor 按 feature 取项 · 缺失 null', () => {
    expect(quotaItemFor(me, 'diagnose')?.used).toBe(3)
    expect(quotaItemFor(me, 'unknown')).toBeNull()
    expect(quotaItemFor(undefined, 'diagnose')).toBeNull()
  })
})

describe('429 detail 解析(后端六字段结构化 dict)', () => {
  const detail = {
    error: 'quota_exceeded', feature: 'diagnose', plan: 'free',
    limit: 20, used: 20, reset_at: '2026-06-14T00:00:00+08:00',
  }

  it('合法 dict → 解析 + 友好文案(数字如实)', () => {
    const d = parseQuotaDetail(detail)
    expect(d).not.toBeNull()
    expect(quotaErrorMessage(d!)).toBe('今日额度已用完(20/20),明日 0 点重置(UTC+8)')
  })

  it('形状不符 → null(走通用错误文案,不误判)', () => {
    expect(parseQuotaDetail('HTTP 429')).toBeNull()
    expect(parseQuotaDetail(null)).toBeNull()
    expect(parseQuotaDetail({ error: 'other' })).toBeNull()
    expect(parseQuotaDetail({ error: 'quota_exceeded', limit: 'x' })).toBeNull()
  })
})

describe('planLabel', () => {
  it('free/pro 映射 · 未知透出', () => {
    expect(planLabel('free')).toBe('免费版')
    expect(planLabel('pro')).toBe('进阶版 Pro')
    expect(planLabel('vip')).toBe('vip')
  })
})
