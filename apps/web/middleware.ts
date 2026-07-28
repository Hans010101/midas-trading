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
 *    仅 GET · 非重定向(<300)· 排除已知 bot UA · ★排除 Next 预取请求(见下 Bug B)。
 *  - UV 去重靠匿名 cookie mid_vid(随机 hex · 无个人信息 · 1 年)· 首访下发。
 *  - 性能红线:只读 cookie + 判定;beacon 用 event.waitUntil fire-and-forget(响应返回后后台发,
 *    绝不阻塞页面)→ 内网 POST /track/visit,FastAPI 侧只 bump Redis(O(1))。隐私:只送匿名 vid。
 *
 * ★2026-07-07 两个 P0 修复(流量归因诊断 · 埋点判定纯函数已抽到 lib/track/beacon-rules.ts):
 *  - Bug A(来源污染):自指判断的 selfHost 改用 req.headers.get('host')(Caddy 正确透传 apex),
 *    不再用 req.nextUrl.hostname(standalone 下 = 内网 host → 自指失效 → 站内跳转误记 referral)。
 *  - Bug B(PV 虚高):isPrefetchRequest 认 Next 15 预取头 → 预取请求不计 PV;真软导航照常计。
 */

import { auth } from '@/auth'
import { NextResponse } from 'next/server'
import type { NextFetchEvent, NextRequest } from 'next/server'

import { BOT_RE, classifyCrawler, extractRefHost, isPrefetchRequest } from '@/lib/track/beacon-rules'

// /workbench 不在保护列表 · 匿名可访问看图
// /admin:未登录跳登录(仅 UX · 真正边界 = 后端 AdminDep 403,普通用户进页也只看到无权限提示)
const PROTECTED = ['/account', '/settings', '/portfolio', '/dashboard', '/admin']
const AUTH_PAGES = ['/login', '/register']

const VID_COOKIE = 'mid_vid'
const VID_MAX_AGE = 60 * 60 * 24 * 365 // 1 年

// 原路由保护逻辑(auth 包装 · 提供 req.auth)
const runAuth = auth((req) => {
  const url = req.nextUrl
  const isAuthed = !!req.auth

  // 商业会员暂停：历史页面代码保留，但不再提供邀请与兑换入口。
  if (url.pathname.startsWith('/account/invite')) {
    return NextResponse.redirect(
      new URL('/account/membership', req.nextUrl.origin),
    )
  }
  if (url.pathname.startsWith('/admin/redeem-codes')) {
    return NextResponse.redirect(new URL('/admin', req.nextUrl.origin))
  }

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

  // ── 访问埋点 · 仅页面文档 GET · 非重定向(<300)──
  const ua = req.headers.get('user-agent') ?? ''
  // 内网直连优先(http://api:8000)· 退化到公网 API base(NEXT_PUBLIC_API_URL 已 inline)
  const base = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL
  const secret = process.env.TRACK_INGEST_SECRET
  const postTrack = (path: string, body: Record<string, string>) => {
    if (!base) return
    event.waitUntil(
      fetch(`${base}${path}`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          ...(secret ? { 'x-track-secret': secret } : {}),
        },
        body: JSON.stringify(body),
      }).catch(() => {
        // 埋点 fire-and-forget · 失败静默(绝不影响页面)
      }),
    )
  }
  const isGetOk = req.method === 'GET' && res.status < 300

  // SEO 批6:AI/搜索爬虫计数(GEO 领先指标)· bot UA 独立于 PV 计。★只发 bot 名 · UA 不发。
  //   爬虫不跑 Next 客户端、不会带预取头,故与下方 PV 的预取排除无关(爬虫计数不受 Bug B 修复影响)。
  if (isGetOk) {
    const bot = classifyCrawler(ua)
    if (bot) postTrack('/api/v1/track/crawler', { bot })
  }

  // ── 人类 PV/UV(排除 bot + ★排除 Next 预取)+ 来源归因 ──
  //   ★Bug B:预取请求(next-router-prefetch 等)是推测加载、非真实浏览 → 不计 PV;
  //   真软导航(点击)不带预取头 → isPrefetchRequest=false → 照常计 PV。
  const isPageView = isGetOk && !BOT_RE.test(ua) && !isPrefetchRequest(req.headers)
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
    // SEO 批6:来源归因(★D8:只取 referer 域名 host + utm_source · 不取 path/query · 不发 IP/UA)
    //   ★Bug A:selfHost 传 req.headers.get('host')(Caddy header_up Host {host} 正确透传 apex),
    //   不传 req.nextUrl.hostname(standalone 下为内网 host → 站内跳转自指判断会失效)。
    const refHost = extractRefHost(req.headers.get('referer'), req.headers.get('host'))
    const utm = (req.nextUrl.searchParams.get('utm_source') ?? '').slice(0, 64)
    postTrack('/api/v1/track/visit', {
      visitor_id: vid,
      ...(refHost ? { ref_host: refHost } : {}),
      ...(utm ? { utm_source: utm } : {}),
    })
  }

  return res
}

// 不拦截静态资源 / API 路由 / _next 内部(带扩展名的静态资源由 .*\..* 排除)
export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)'],
}
