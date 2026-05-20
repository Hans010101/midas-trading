/**
 * Next.js middleware · 路由保护。
 *
 * 0006 ADR § 8:
 *  - 未登录访问受保护路径(/workbench, /dashboard) → /login?next=...
 *  - 已登录访问 /login or /register → /workbench
 */

import { auth } from '@/auth'
import { NextResponse } from 'next/server'

const PROTECTED = ['/workbench', '/dashboard', '/portfolio', '/settings']
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
    return NextResponse.redirect(new URL('/workbench', req.nextUrl.origin))
  }

  return NextResponse.next()
})

// 不拦截静态资源 / API 路由 / _next 内部
export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)'],
}
