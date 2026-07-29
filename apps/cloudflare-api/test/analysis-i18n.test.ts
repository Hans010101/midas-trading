import { describe, expect, it } from 'vitest'

import {
  requestLanguage,
  technicalDecisionFallback,
} from '../src/analysis'

const snapshot = {
  last_close: 100,
  change_20_bars_pct: -4.2,
  ma5: 96,
  ma20: 101,
  ma60: 104,
  rsi14: 34,
  volatility_20_bars_pct: 2.1,
  recent_high: 112,
  recent_low: 94,
}

describe('analysis language', () => {
  it('uses the explicit X-Lang request header', () => {
    expect(requestLanguage(new Request('https://api.test'))).toBe('zh')
    expect(requestLanguage(new Request('https://api.test', {
      headers: { 'X-Lang': 'en-US' },
    }))).toBe('en')
  })

  it('keeps the technical fallback fully English', () => {
    const output = technicalDecisionFallback(snapshot, 'en')
    expect(output.rationale).toContain('RSI(14)')
    expect(output.plan_note).toContain('recent high')
    expect(`${output.rationale} ${output.plan_note}`).not.toMatch(
      /[\u3400-\u9fff]/u,
    )
  })
})
