import { describe, expect, it } from 'vitest'

import { isIndependentApiPath } from './api-route-policy'

describe('isIndependentApiPath', () => {
  it('keeps authenticated AI routes on the independent Cloudflare API', () => {
    expect(isIndependentApiPath('/api/v1/analysis/decision-card')).toBe(true)
    expect(isIndependentApiPath('/api/v1/analysis/strategy-signals')).toBe(true)
    expect(isIndependentApiPath('/api/v1/analysis/strategy-recommend')).toBe(true)
    expect(isIndependentApiPath('/api/v1/structure/diagnose')).toBe(true)
  })

  it('fails closed on every v1 path instead of forwarding to the legacy API', () => {
    expect(isIndependentApiPath('/api/v1/analysis/chan')).toBe(true)
    expect(isIndependentApiPath('/api/v1/analysis/weekly-report')).toBe(true)
    expect(isIndependentApiPath('/api/v1/retired-feature')).toBe(true)
    expect(isIndependentApiPath('/external/path')).toBe(false)
  })

  it('keeps authentication and market data on the independent API', () => {
    expect(isIndependentApiPath('/api/v1/auth/login')).toBe(true)
    expect(isIndependentApiPath('/api/v1/crypto/market/BTCUSDT')).toBe(true)
    expect(isIndependentApiPath('/api/v1/track/visit')).toBe(true)
  })

  it('keeps every administrator route on the independent Cloudflare API', () => {
    expect(isIndependentApiPath('/api/v1/admin/overview')).toBe(true)
    expect(isIndependentApiPath('/api/v1/admin/users')).toBe(true)
    expect(isIndependentApiPath('/api/v1/admin/support-tickets')).toBe(true)
    expect(isIndependentApiPath('/api/v1/admin/academy-stats')).toBe(true)
  })
})
