/** 会员门槛关闭后，做T通知对注册用户始终开放。 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { DottAlertView } from './notifications-config-section'

const noop = () => {}

describe('DottAlertView · registered access', () => {
  it('会员状态不会阻断两个通知开关', () => {
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
    expect(html).not.toContain('Pro 专属')
    expect(html).not.toContain('开通 Pro')
    expect(html.match(/type="checkbox"/g)?.length).toBe(2)
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
