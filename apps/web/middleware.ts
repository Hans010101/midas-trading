/**
 * Next.js middleware · 路由保护 + 访问埋点(服务端 · 非浏览器 JS)。
 *
 * 路由保护(0006 ADR § 8 + M1 第三波):
 *  - /workbench 匿名可访问(未登录看 K 线 / 缠论 / AI 决策卡)· 需登录操作由组件 useRequireAuth() 弹引导
 *  - /account / /settings / /portfolio / /admin 强制登录;已登录访问 /login·/register → /global
 *
 * 访问埋点(网站访问看板 · PV/UV):
 *  - 页面请求只到 web(Next)容器(Caddy 把 /api 路由到 FastAPI)→ ★只有这层看得到页面访问,
 *    故埋点放此(服务端 Edge · 非浏览器 JS · 关 JS / 拦截不失真)。
 *  - matcher 已天然排除 api / _next / 所有带扩展名的静态资源(js/css/png/woff/map);此处再补:
 *    仅 GET · 非重定向(<300)· 排除已知 bot UA。
 *  - UV 去重靠匿名 cookie mid_vid(随机 hex · 无个人信息 · 1 年)· 首访下发。
 *  - 性能红线:只读 cookie + 判定;beacon 用 event.waitUntil fire-and-forget(响应返回后后台发,
 *    绝不阻塞页面)→ 内网 POST /track/visit,FastAPI 侧只 bump Redis(O(1))。隐私:只送匿名 vid。
 */

import { auth } from '@/auth'
import { NextResponse } from 'next/server'
import type { NextFetchEvent, NextRequest } from 'next/server'

// /workbench 不在保护列表 · 匿名可访问看图
// /admin:未登录跳登录(仅 UX · 真正边界 = 后端 AdminDep 403,普通用户进页也只看到无权限提示)
const PROTECTED = ['/account', '/settings', '/portfolio', '/dashboard', '/admin']
const AUTH_PAGES = ['/login', '/register']

const VID_COOKIE = 'mid_vid'
const VID_MAX_AGE = 60 * 60 * 24 * 365 // 1 年
// 已知爬虫 / 预览抓取 / 监控 / 脚本 UA → 不计入 PV(避免被机器人刷爆)
const BOT_RE =
  /bot|crawl|spider|slurp|bing|baidu|yandex|duckduck|facebookexternalhit|embedly|quora|pinterest|slackbot|telegram|whatsapp|headless|lighthouse|monitor|uptime|pingdom|curl|wget|python-requests|go-http|axios|okhttp|java\//i

// 原路由保护逻辑(auth 包装 · 提供 req.auth)
const runAuth = auth((req) => {
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
    )(req, event)) ?? NextResponse.next()

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

// 不拦截静态资源 / API 路由 / _next 内部(带扩展名的静态资源由 .*\..* 排除)
export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)'],
}
