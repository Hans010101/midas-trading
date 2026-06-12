/**
 * Next.js middleware · 路由保护。
 *
 * 0006 ADR § 8 + M1 第三波(2026-05-21 产品负责人指令):
 *  - /workbench 改匿名可访问(未登录看 K 线 / 缠论 / AI 决策卡)·
 *    具体「需登录」操作(下单 / 加自选 / 设虚拟资金 / 保存绘图)
 *    由前端组件用 useRequireAuth() 弹登录引导,不在 middleware 拦截
 *  - /account / /settings / /portfolio 仍强制登录
 *  - 已登录访问 /login or /register → /global(ADR 0035 · 全球概览为市场默认落地页)
 */

import { auth } from '@/auth'
import { NextResponse } from 'next/server'

// /workbench 不在保护列表 · 匿名可访问看图
// /admin:未登录跳登录(仅 UX · 真正边界 = 后端 AdminDep 403,普通用户进页也只看到无权限提示)
const PROTECTED = ['/account', '/settings', '/portfolio', '/dashboard', '/admin']
const AUTH_PAGES = ['/login', '/register']

export default auth((req) => {
  const url = req.nextUrl
  const isAuthed = !!req.auth

  const isProtected = PROTECTED.some((p) => url.pathname.startsWith(p))
  const isAuthPage = AUTH_PAGES.some((p) => url.pathname.startsWith(p))

  if (isProtected && !isAuthed) {
    const loginUrl = new URL('/login', req.nextUrl.origin)
    loginUrl.searchParams.set('next', url.pathname + url.search)
    return NextResponse.redirect(loginUrl)
  }

  if (isAuthPage && isAuthed) {
    return NextResponse.redirect(new URL('/global', req.nextUrl.origin))
  }

  return NextResponse.next()
})

// 不拦截静态资源 / API 路由 / _next 内部
export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)'],
}
