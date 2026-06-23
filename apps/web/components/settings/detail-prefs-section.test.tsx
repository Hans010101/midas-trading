/** 详情页默认偏好 section 渲染测(刀1 · 登录墙页用 renderToString 钉死 · 同 quota-hint 范式)。
 *
 * renderToString 不跑 useEffect → 渲染初始 useState(系统默认)。
 * ★做T重构(B-2):做T 开关已移除(做T 改走主图策略面板「布林做T」标签常显)· 此处只剩 3 个图层。
 * cookie 读写往返由 lib/display-prefs.test.ts(jsdom)覆盖。
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { DetailPrefsSection } from './detail-prefs-section'

describe('DetailPrefsSection 渲染(默认态)', () => {
  const html = renderToString(<DetailPrefsSection />)

  it('标题 + 3 个指标图层 + 默认周期 + 浏览器保存文案', () => {
    expect(html).toContain('详情页默认显示')
    for (const label of ['布林带', '缠论标注', 'MACD']) {
      expect(html).toContain(label)
    }
    for (const p of ['15m', '1h', '1d']) {
      expect(html).toContain(`>${p}<`)
    }
    expect(html).toContain('按浏览器保存')
  })

  it('★做T 开关已移除:只剩 3 个图层 switch(布林/缠论/MACD 默认全开)+ 无「做T结构」', () => {
    // 3 个 role=switch · aria-checked 顺序 = boll/chan/macd(数组顺序)· 全默认开
    const checks = [...html.matchAll(/role="switch"[^>]*aria-checked="(true|false)"/g)].map(
      (m) => m[1],
    )
    expect(checks).toEqual(['true', 'true', 'true']) // ★3 个 · 无 dott toggle
    expect(html).not.toContain('做T结构') // ★做T 开关 + 说明已移除
  })

  it('默认周期 1h 选中(aria-pressed=true)', () => {
    // 1h 的按钮 aria-pressed=true · 15m/1d=false
    expect(html).toMatch(/aria-pressed="true"[^>]*>1h<|>1h<[^>]*aria-pressed="true"/)
  })
})
