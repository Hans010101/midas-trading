/**
 * 邀请码 ref 归因 cookie 读写纯函数(Phase 1.5 刀B)· vitest 可测。
 *
 * 为什么走 cookie:Google OAuth 回跳后 ?ref= 查询参数丢失(NextAuth 在
 * /api/auth/* 中转),callbackUrl 只在前端流转后端拿不到(G 调研定);
 * register 页落地即写 cookie,signIn callback(server-side)用 next/headers
 * cookies() 读出 → 进 /oauth/google body。邮箱注册不依赖 cookie(直接进 payload)。
 */

export const REF_COOKIE = 'midas_ref'
const MAX_AGE_DAYS = 30

/** ref 归一:trim + 大写 + 长度 ≤12(后端 invite_code VARCHAR(12))· 非法返回 null。 */
export function normalizeRef(raw: string | null | undefined): string | null {
  if (!raw) return null
  const code = raw.trim().toUpperCase()
  if (code === '' || code.length > 12) return null
  return code
}

/** document.cookie 写入串(client-side · register 页落地调用)。 */
export function buildRefCookie(code: string): string {
  const maxAge = MAX_AGE_DAYS * 24 * 60 * 60
  return `${REF_COOKIE}=${encodeURIComponent(code)}; path=/; max-age=${maxAge}; samesite=lax`
}

/** 从 cookie 串(document.cookie 或 server 拼接)解析 ref · 缺失返回 null。 */
export function readRefFromCookieString(cookieString: string | null | undefined): string | null {
  if (!cookieString) return null
  const m = cookieString.match(new RegExp(`(?:^|; )${REF_COOKIE}=([^;]+)`))
  return m ? normalizeRef(decodeURIComponent(m[1])) : null
}
