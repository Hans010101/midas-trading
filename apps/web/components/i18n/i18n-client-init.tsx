'use client'

/**
 * i18n 客户端初始化(cookie-locale · 决策 A · docs/i18n/cookie-locale-design.md)· 渲染 null。
 *
 * 两件事:
 * ① ★X-Lang 全站零漏注入:monkey-patch window.fetch,给所有打到后端(NEXT_PUBLIC_API_URL)的
 *    请求注入 `X-Lang: <当前 NEXT_LOCALE cookie>` 头 → 后端 resolve_lang 最高优先级命中(生产已验)。
 *    ★为何 monkey-patch:前端无统一 API client(37 个 lib/api 文件各自散装 fetch·111 处调用),
 *    逐文件改必漏且防不住未来新增;patch 一处 scoped 到 API_BASE = 自动覆盖全部 client fetch +
 *    未来新增(Explore 盘点:37/37 用 API_BASE·100% 客户端·经 window.fetch)。埋点(middleware
 *    server-side edge)不经 window.fetch 也不需 X-Lang,天然排除。
 * ② 登录跨设备同步(决策 4):登录用户 language_pref 与本设备 cookie 不一致时,把 pref 写进 cookie
 *    + refresh 一次 → 换设备登录语言跟随(之后全走 cookie 单一真相源 · 幂等不重复 refresh)。
 */

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

import { useMe } from '@/hooks/use-me'
import { getLocaleCookie, setLocaleCookie } from '@/lib/i18n/locale-cookie'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

let fetchPatched = false

/** 给打到后端的 client fetch 注入 X-Lang(读实时 cookie · 只打一次补丁 · 失败绝不阻塞请求)。 */
function patchFetch(): void {
  if (fetchPatched || typeof window === 'undefined') return
  fetchPatched = true
  const orig = window.fetch
  window.fetch = function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    try {
      const url =
        typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url && url.startsWith(API_BASE)) {
        const headers = new Headers(init?.headers)
        // input 是 Request 且 init 未覆盖 headers → 补上 Request 自带头(不丢原头)
        if (!init?.headers && input instanceof Request) {
          input.headers.forEach((v, k) => headers.set(k, v))
        }
        if (!headers.has('X-Lang')) headers.set('X-Lang', getLocaleCookie())
        return orig.call(this, input, { ...init, headers })
      }
    } catch {
      // 注入失败绝不阻塞请求 · 退回原始 fetch
    }
    return orig.call(this, input, init)
  }
}

// 模块加载即打补丁(client bundle 载入时 · 早于组件 effect · 覆盖首屏后所有 client fetch)。
patchFetch()

export function I18nClientInit() {
  const { data: me } = useMe()
  const router = useRouter()

  // effect 兜底(极端情况模块级未执行)· 幂等
  useEffect(() => {
    patchFetch()
  }, [])

  // 登录跨设备同步:pref 与本设备 cookie 不一致 → 写 cookie + refresh(仅在真不一致时·幂等不循环)
  useEffect(() => {
    const pref = me?.language_pref
    if ((pref === 'zh' || pref === 'en') && getLocaleCookie() !== pref) {
      setLocaleCookie(pref)
      router.refresh()
    }
  }, [me?.language_pref, router])

  return null
}
