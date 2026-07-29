import { describe, expect, it } from 'vitest'

import type { EconEvent } from '@/lib/api/econ-calendar'
import {
  cnCompanyNameFromOriginal,
  cnSectorName,
  cnStockName,
  econEventTitle,
  hkSectorName,
  hkStockName,
  usSectorName,
  usStockName,
} from '@/lib/i18n/market-copy'

const CJK_RE = /[\u3400-\u9fff]/

describe('market page English copy', () => {
  it('maps calendar events while preserving the Chinese source title', () => {
    const event: EconEvent = {
      event_key: 'fomc-2026-07-29',
      event_type: 'fomc',
      title: 'FOMC 利率决议',
      markets: ['us', 'crypto'],
      importance: 3,
      scheduled_at: '2026-07-30T02:00:00+08:00',
      time_confirmed: true,
      source: 'fed_json',
    }
    expect(econEventTitle(event, 'zh')).toBe('FOMC 利率决议')
    expect(econEventTitle(event, 'en')).toBe('FOMC Rate Decision')
  })

  it('never leaks Chinese from an unknown calendar event in English mode', () => {
    const event: EconEvent = {
      event_key: 'future-event',
      event_type: 'future_event',
      title: '未来新增事件',
      markets: ['cn'],
      importance: 1,
      scheduled_at: '2026-08-01T09:00:00+08:00',
      time_confirmed: false,
      source: 'seed',
    }
    expect(econEventTitle(event, 'en')).not.toMatch(CJK_RE)
  })

  it('maps current A-share companies and sectors and has English fallbacks', () => {
    expect(cnStockName('300750', '宁德时代', 'en')).toBe('CATL')
    expect(cnStockName('999999', '未知公司', 'en')).toBe('A-share 999999')
    expect(cnCompanyNameFromOriginal('贵州茅台', 'en')).toBe('Kweichow Moutai')
    expect(cnSectorName('新能源', 'en')).toBe('New Energy')
    expect(cnSectorName('未来板块', 'en', 8)).toBe('China Sector 9')
  })

  it('leaves Chinese market data unchanged in Chinese mode', () => {
    expect(cnStockName('300750', '宁德时代', 'zh')).toBe('宁德时代')
    expect(cnCompanyNameFromOriginal('贵州茅台', 'zh')).toBe('贵州茅台')
    expect(cnSectorName('新能源', 'zh')).toBe('新能源')
  })

  it('translates the curated U.S. market universe without leaking CJK', () => {
    expect(usStockName('NFLX', '奈飞', 'en')).toBe('Netflix')
    expect(usStockName('AAPL', '苹果', 'en')).toBe('Apple')
    expect(usSectorName('中概股', 'en')).toBe('China ADRs')
    expect(usStockName('TEST', '测试公司', 'en')).toBe('U.S. stock TEST')
  })

  it('translates the curated Hong Kong universe without leaking CJK', () => {
    expect(hkStockName('00700', '腾讯控股', 'en')).toBe('Tencent Holdings')
    expect(hkStockName('00388', '香港交易所', 'en')).toBe(
      'Hong Kong Exchanges and Clearing',
    )
    expect(hkSectorName('电信', 'en')).toBe('Telecommunications')
    expect(hkStockName('09900', '测试公司', 'en')).toBe('HK stock 09900')
  })
})
