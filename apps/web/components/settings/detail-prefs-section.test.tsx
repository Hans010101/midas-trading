/** 详情页默认偏好 section 渲染测(刀1 · 登录墙页用 renderToString 钉死 · 同 quota-hint 范式)。
 *
 * renderToString 不跑 useEffect → 渲染初始 useState(系统默认)· 正好验「★做T 默认关 + 默认结构」。
 * cookie 读写往返由 lib/display-prefs.test.ts(jsdom)覆盖。
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { DetailPrefsSection } from './detail-prefs-section'

describe('DetailPrefsSection 渲染(默认态)', () => {
  const html = renderToString(<DetailPrefsSection />)

  it('标题 + 4 个指标图层 + 做T说明 + 默认周期 + 浏览器保存文案', () => {
    expect(html).toContain('详情页默认显示')
    for (const label of ['布林带', '缠论标注', 'MACD', '做T结构']) {
      expect(html).toContain(label)
    }
    expect(html).toContain('控制详情页是否显示做T结构模块')
    for (const p of ['15m', '1h', '1d']) {
      expect(html).toContain(`>${p}<`)
    }
    expect(html).toContain('按浏览器保存')
  })

  it('★做T 默认关:dott 的 switch aria-checked=false,其余三个 true', () => {
    // 4 个 role=switch · aria-checked 顺序 = boll/chan/macd/dott(数组顺序)
    const checks = [...html.matchAll(/role="switch"[^>]*aria-checked="(true|false)"/g)].map(
      (m) => m[1],
    )
    expect(checks).toEqual(['true', 'true', 'true', 'false']) // ★dott=false
  })

  it('默认周期 1h 选中(aria-pressed=true)', () => {
    // 1h 的按钮 aria-pressed=true · 15m/1d=false
    expect(html).toMatch(/aria-pressed="true"[^>]*>1h<|>1h<[^>]*aria-pressed="true"/)
  })
})
