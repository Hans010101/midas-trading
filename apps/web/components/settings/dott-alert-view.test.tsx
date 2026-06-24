/** 做T信号卡 Pro 门控两态(做T M2-2)· 登录墙页用 renderToString 钉死(替代截图)。
 *
 * DottAlertView 是 props 驱动纯展示(无 hooks)· 测非 Pro(禁用+Pro徽章+开通引导)/ Pro(可开关)两态。
 * 后端 Pro 二道 gate(非 Pro 设 true→403)由 apps/api test_notifications.py 覆盖。
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { DottAlertView } from './notifications-config-section'

const noop = () => {}

describe('DottAlertView · Pro 门控两态', () => {
  it('★非 Pro:开关禁用(无 checkbox)+「Pro 专属」徽章 +「开通 Pro」引导', () => {
    const html = renderToString(
      <DottAlertView
        isPro={false}
        bound={false}
        enabled={false}
        pending={false}
        onToggle={noop}
        onUpgrade={noop}
      />,
    )
    expect(html).toContain('做T信号推送')
    expect(html).toContain('Pro 专属') // 标题徽章
    expect(html).toContain('Pro 会员专属') // 禁用态文案
    expect(html).toContain('开通 Pro') // 引导
    // ★非 Pro 没有可操作的开关(Toggle 的 checkbox 不渲染)
    expect(html).not.toContain('type="checkbox"')
  })

  it('★Pro + 已绑 TG:渲染可操作开关(checkbox)· 无「开通 Pro」', () => {
    const html = renderToString(
      <DottAlertView
        isPro
        bound
        enabled={false}
        pending={false}
        onToggle={noop}
        onUpgrade={noop}
      />,
    )
    expect(html).toContain('做T信号 TG 通知')
    expect(html).toContain('type="checkbox"') // ★可操作开关在
    expect(html).not.toContain('开通 Pro')
    expect(html).toContain('推到你的 Telegram')
  })

  it('★Pro + 已订阅(enabled)→ 开关勾选 + 显「开」', () => {
    const html = renderToString(
      <DottAlertView isPro bound enabled pending={false} onToggle={noop} onUpgrade={noop} />,
    )
    expect(html).toContain('checked')
    expect(html).toContain('>开<')
  })

  it('Pro + 未绑 TG:提示先绑定 Telegram', () => {
    const html = renderToString(
      <DottAlertView
        isPro
        bound={false}
        enabled={false}
        pending={false}
        onToggle={noop}
        onUpgrade={noop}
      />,
    )
    expect(html).toContain('需先绑定 Telegram')
  })
})
