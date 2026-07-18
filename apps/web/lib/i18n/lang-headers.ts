/**
 * 给后端 fetch 加 X-Lang 头(cookie locale → 后端 resolve_lang)。
 *
 * ★★绝不做全局 window.fetch monkey-patch —— #4 翻车(feat/i18n-fe-cookie-p2)血证:
 *   `window.fetch = function(){ orig.call(this,…) }` 转发 caller 的 `this`(非 Window)
 *   → 原生 fetch 抛 "Illegal invocation" → 全站后端不可达。故改【逐 API 模块显式合并】——
 *   安全(不碰全局)、可控、可 grep(能查到每个注入点)。
 *
 * 注:登录用户即使不带 X-Lang,后端也会按其 language_pref 出对应语言(resolve_lang 扩回 level②);
 *   本头主要覆盖 guest 调用 + 让语言切换在 PATCH 落库前即时生效。zh 也照发(后端 normalize 幂等)。
 */
import { getLocaleCookie } from '@/lib/i18n/locale-cookie'

/** 合并 X-Lang(不覆盖调用方已显式设的 X-Lang)· 返回可直接给 fetch 的 Headers。 */
export function withLang(headers?: HeadersInit): Headers {
  const merged = new Headers(headers)
  if (!merged.has('X-Lang')) merged.set('X-Lang', getLocaleCookie())
  return merged
}
