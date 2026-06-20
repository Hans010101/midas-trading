/** 结业庆祝动画组件渲染单测(刀3)· renderToString 钉死(登录墙+需提交·preview 难触发)。 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { Celebration } from './celebration'

describe('Celebration 庆祝动画', () => {
  it('渲染标题 + 会员副标题 + 纸屑 + 关闭按钮', () => {
    const html = renderToString(
      <Celebration
        title="🎉 恭喜完成「合约与衍生品」结业测验!"
        subtitle="已为你增加 1 周会员 · 会员有效期至 2026-06-27"
        onClose={() => {}}
      />,
    )
    expect(html).toContain('恭喜完成')
    expect(html).toContain('已为你增加 1 周会员')
    expect(html).toContain('会员有效期至 2026-06-27')
    expect(html).toContain('midas-confetti') // ★纸屑在(纯CSS·不引库)
    expect(html).toContain('知道了') // 关闭按钮
  })

  it('无副标题也安全', () => {
    const html = renderToString(<Celebration title="恭喜" onClose={() => {}} />)
    expect(html).toContain('恭喜')
    expect(html).toContain('midas-confetti')
  })
})
