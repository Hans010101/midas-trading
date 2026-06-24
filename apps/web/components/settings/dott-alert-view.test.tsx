/** 做T信号卡 Pro 门控两态(做T M2-4 拆两开关)· 登录墙页用 renderToString 钉死(替代截图)。
 *
 * DottAlertView props 驱动纯展示(无 hooks)· 测非 Pro(两开关禁用+Pro徽章+开通引导)/
 * Pro(两开关可操作:做T定时全景 + 做T行情转换)两态。后端两字段 Pro 二道 gate 由
 * apps/api test_notifications.py(test_dott_split_*)覆盖。
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { DottAlertView } from './notifications-config-section'

const noop = () => {}

describe('DottAlertView · Pro 门控两态(M2-4 两开关)', () => {
  it('★非 Pro:无可操作开关(无 checkbox)+「Pro 专属」徽章 +「开通 Pro」引导', () => {
    const html = renderToString(
      <DottAlertView
        isPro={false}
        bound={false}
        digestEnabled={false}
        transitionEnabled={false}
        pending={false}
        onToggleDigest={noop}
        onToggleTransition={noop}
        onUpgrade={noop}
      />,
    )
    expect(html).toContain('做T信号推送')
    expect(html).toContain('Pro 专属') // 标题徽章
    expect(html).toContain('Pro 会员专属') // 禁用态文案
    expect(html).toContain('开通 Pro') // 引导
    // ★非 Pro 没有可操作开关(两个 Toggle 的 checkbox 都不渲染)
    expect(html).not.toContain('type="checkbox"')
  })

  it('★Pro:两个开关都渲染(做T定时全景 + 做T行情转换 · 各一个 checkbox)', () => {
    const html = renderToString(
      <DottAlertView
        isPro
        bound
        digestEnabled={false}
        transitionEnabled={false}
        pending={false}
        onToggleDigest={noop}
        onToggleTransition={noop}
        onUpgrade={noop}
      />,
    )
    expect(html).toContain('做T定时全景')
    expect(html).toContain('做T行情转换')
    expect(html).not.toContain('开通 Pro')
    // ★两个可操作开关(两个 checkbox)
    expect(html.match(/type="checkbox"/g)?.length).toBe(2)
  })

  it('★Pro + 两开关分别勾选 → 各自独立反映', () => {
    const html = renderToString(
      <DottAlertView
        isPro
        bound
        digestEnabled
        transitionEnabled={false}
        pending={false}
        onToggleDigest={noop}
        onToggleTransition={noop}
        onUpgrade={noop}
      />,
    )
    // 至少一个开(digest)+ 一个关(transition)→ 同时含「开」与「关」标
    expect(html).toContain('>开<')
    expect(html).toContain('>关<')
  })

  it('Pro + 未绑 TG:提示先绑定 Telegram', () => {
    const html = renderToString(
      <DottAlertView
        isPro
        bound={false}
        digestEnabled={false}
        transitionEnabled={false}
        pending={false}
        onToggleDigest={noop}
        onToggleTransition={noop}
        onUpgrade={noop}
      />,
    )
    expect(html).toContain('需先绑定 Telegram')
  })
})
