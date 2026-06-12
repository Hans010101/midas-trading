/** 管理页展示纯逻辑单测(用户管理刀2)。 */

import { describe, expect, it } from 'vitest'

import { createdAtText, lastActiveText, registerMethodLabel } from './admin-view'

describe('registerMethodLabel(注册方式徽标)', () => {
  it('三态映射:google / password / both', () => {
    expect(registerMethodLabel('google')).toBe('Google')
    expect(registerMethodLabel('password')).toBe('邮箱')
    expect(registerMethodLabel('both')).toBe('Google+邮箱')
  })

  it('未知值原样透出(后端新增方式不至于显示空白)', () => {
    expect(registerMethodLabel('sso')).toBe('sso')
  })
})

describe('lastActiveText(7d 口径文案)', () => {
  it('null → 「7 天内无活跃」(session 7 天滚动 TTL · 无未过期 session)', () => {
    expect(lastActiveText(null)).toBe('7 天内无活跃')
  })

  it('非 null → 本地化到分钟(含月日时分)', () => {
    const text = lastActiveText('2026-06-12T08:30:00Z')
    expect(text).not.toBe('7 天内无活跃')
    expect(text).toMatch(/\d{2}/)
  })

  it('非法时间字符串 → 兜底「7 天内无活跃」不渲染 Invalid Date', () => {
    expect(lastActiveText('not-a-date')).toBe('7 天内无活跃')
  })
})

describe('createdAtText(注册时间 · 日期粒度)', () => {
  it('ISO → zh-CN 日期 · 非法原样透出', () => {
    expect(createdAtText('2026-05-19T00:00:00Z')).toMatch(/2026/)
    expect(createdAtText('garbage')).toBe('garbage')
  })
})
