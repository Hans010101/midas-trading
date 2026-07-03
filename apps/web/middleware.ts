/**
 * Next.js middleware · ★i18n locale 检测/重写 + 路由保护 + 访问埋点(三合一)。
 *
 * 顺序(不可乱):next-intl createMiddleware 最先(locale 检测/重写:as-needed 下 `/` 命中
 *   中文 [locale] 段、`/en/*` 校验),再叠 auth 路由保护,最后 PV/UV 埋点 —— 后两步都要读
 *   【剥掉 locale 前缀后】的路径判定(否则 /en/account 的 startsWith('/account') 失效 = 安全洞)。
 *
 * 路由保护(0006 ADR § 8 + M1 第三波):
 *  - /workbench 匿名可访问 · /account /settings /portfolio /admin 强制登录 · 已登录访问 /login·/register → /global
 *  - ★i18n 激活:PROTECTED/AUTH_PAGES 判定走【剥 locale 前缀后】的路径,重定向目标带回当前 locale 前缀。
 *
 * 访问埋点(网站访问看板 · PV/UV):服务端 Edge · 匿名 vid cookie · waitUntil fire-and-forget。
 */

import { auth } from '@/auth'
import createMiddleware from 'next-intl/middleware'
import { NextResponse } from 'next/server'
import type { NextFetchEvent, NextRequest } from 'next/server'

import { routing } from '@/i18n/routing'

// ★localeDetection 关闭见 i18n/routing.ts(批0 v2 生产 redirect loop 修)· 属 routing 配置。
const intlMiddleware = createMiddleware(routing)

// /workbench 不在保护列表 · 匿名可访问看图
// /admin:未登录跳登录(仅 UX · 真正边界 = 后端 AdminDep 403)
const PROTECTED = ['/account', '/settings', '/portfolio', '/dashboard', '/admin']
const AUTH_PAGES = ['/login', '/register']

// ★as-needed:中文无前缀,只有英文带 /en 前缀。剥出 { prefix, path } 供 locale 感知判定。
//   '/en/account' → {prefix:'/en', path:'/account'};'/account' → {prefix:'', path:'/account'}
function localeInfo(pathname: string): { prefix: string; path: string } {
  if (pathname === '/en' || pathname.startsWith('/en/')) {
    return { prefix: '/en', path: pathname.slice(3) || '/' }
  }
  return { prefix: '', path: pathname }
}

const VID_COOKIE = 'mid_vid'
const VID_MAX_AGE = 60 * 60 * 24 * 365 // 1 年
// 已知爬虫 / 预览抓取 / 监控 / 脚本 UA → 不计入 PV(避免被机器人刷爆)
const BOT_RE =
  /bot|crawl|spider|slurp|bing|baidu|yandex|duckduck|facebookexternalhit|embedly|quora|pinterest|slackbot|telegram|whatsapp|headless|lighthouse|monitor|uptime|pingdom|curl|wget|python-requests|go-http|axios|okhttp|java\//i

// 路由保护逻辑(auth 包装 · 提供 req.auth)· 通过校验后委托 next-intl 做 locale 重写。
const runAuth = auth((req) => {
  const url = req.nextUrl
  const isAuthed = !!req.auth
  const { prefix, path } = localeInfo(url.pathname) // ★locale 感知

  const isProtected = PROTECTED.some((p) => path.startsWith(p))
  const isAuthPage = AUTH_PAGES.some((p) => path.startsWith(p))

  if (isProtected && !isAuthed) {
    // 保留当前 locale 前缀跳登录(英文用户跳 /en/login)· next 带原始含前缀路径
    const loginUrl = new URL(`${prefix}/login`, url.origin)
    loginUrl.searchParams.set('next', url.pathname + url.search)
    return NextResponse.redirect(loginUrl)
  }

  if (isAuthPage && isAuthed) {
    return NextResponse.redirect(new URL(`${prefix}/global`, url.origin))
  }

  // 未拦截 → 交给 next-intl 做 locale 检测/重写(as-needed:`/` → 内部中文段、`/en/*` 校验)
  return intlMiddleware(req)
})

function randomVid(): string {
  const b = new Uint8Array(16)
  crypto.getRandomValues(b)
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
}

export default async function middleware(req: NextRequest, event: NextFetchEvent) {
  const res =
    (await (
      runAuth as unknown as (
        r: NextRequest,
        e: NextFetchEvent,
      ) => Promise<NextResponse | undefined>
    )(req, event)) ?? intlMiddleware(req)

  // ── 访问埋点 · 仅页面文档 GET · 非重定向(<300)· 排除 bot ──
  const ua = req.headers.get('user-agent') ?? ''
  const isPageView = req.method === 'GET' && res.status < 300 && !BOT_RE.test(ua)
  if (isPageView) {
    let vid = req.cookies.get(VID_COOKIE)?.value
    if (!vid || vid.length < 8) {
      vid = randomVid()
      // ★ 用 headers.append 写 Set-Cookie:auth() 返回的是普通 Response(无 NextResponse.cookies
      //   助手),res.cookies.set 会 TypeError → 全站 500。headers.append 在普通 Response 也生效。
      const secure = process.env.NODE_ENV === 'production' ? '; Secure' : ''
      res.headers.append(
        'set-cookie',
        `${VID_COOKIE}=${vid}; Path=/; Max-Age=${VID_MAX_AGE}; HttpOnly; SameSite=Lax${secure}`,
      )
    }
    // 内网直连优先(http://api:8000)· 退化到公网 API base(NEXT_PUBLIC_API_URL 已 inline)
    const base = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL
    if (base) {
      const secret = process.env.TRACK_INGEST_SECRET
      event.waitUntil(
        fetch(`${base}/api/v1/track/visit`, {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            ...(secret ? { 'x-track-secret': secret } : {}),
          },
          body: JSON.stringify({ visitor_id: vid }),
        }).catch(() => {
          // 埋点 fire-and-forget · 失败静默(绝不影响页面)
        }),
      )
    }
  }

  return res
}

// 不拦截静态资源 / API 路由 / _next 内部 · 已覆盖 next-intl 需拦的 `/` 与 `/en/*`
export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)'],
}
