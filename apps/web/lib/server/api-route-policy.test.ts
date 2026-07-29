import { describe, expect, it } from 'vitest'

import { isIndependentApiPath } from './api-route-policy'

describe('isIndependentApiPath', () => {
  it('keeps authenticated AI routes on the independent Cloudflare API', () => {
    expect(isIndependentApiPath('/api/v1/analysis/decision-card')).toBe(true)
    expect(isIndependentApiPath('/api/v1/analysis/strategy-signals')).toBe(true)
    expect(isIndependentApiPath('/api/v1/analysis/strategy-recommend')).toBe(true)
    expect(isIndependentApiPath('/api/v1/structure/diagnose')).toBe(true)
  })

  it('does not redirect analysis routes that have not been migrated yet', () => {
    expect(isIndependentApiPath('/api/v1/analysis/chan')).toBe(false)
    expect(isIndependentApiPath('/api/v1/analysis/weekly-report')).toBe(false)
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
