import { describe, expect, it } from 'vitest'

import { ADMIN_TABS } from './admin-nav'

describe('independent administrator navigation', () => {
  it('shows every migrated operation and keeps redeem codes hidden', () => {
    expect(ADMIN_TABS.map((tab) => tab.href)).toEqual([
      '/admin',
      '/admin/visit-stats',
      '/admin/academy-stats',
      '/admin/weekly-dispatch',
      '/admin/reports',
      '/admin/migration',
      '/admin/x-tweets',
      '/admin/managed',
      '/admin/intelligent',
      '/admin/support-tickets',
    ])
    expect(
      ADMIN_TABS.map((tab) => String(tab.href)).includes(
        '/admin/redeem-codes',
      ),
    ).toBe(false)
  })
})
