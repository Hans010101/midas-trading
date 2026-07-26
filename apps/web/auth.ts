/**
 * NextAuth v5(Auth.js)配置。
 *
 * Providers:
 *   1. Credentials · 邮箱密码登录 · 调后端 POST /api/v1/auth/login(0006 ADR · M1)
 *   2. Google · OAuth · 调后端 POST /api/v1/auth/oauth/google(M1 第三波)
 *
 * 0006 ADR 2026-05-21 回归后,后端 access_token 字段仍是这个名字,
 * 内容是 **opaque DB session token**(7 天滚动 TTL + 单用户 5 设备上限)。
 * 前端 NextAuth 把它当 opaque 字符串塞进自己的 cookie · 调用方无感。
 *
 * Google OAuth 桥接:
 *   - NextAuth Google provider 在浏览器侧完成 Google 同意页 + 回调
 *   - signIn callback 拿到 google account.id_token · POST 给后端 /oauth/google
 *   - 后端验签 + find_or_create user · 返回 session token
 *   - signIn callback 把 token 塞到 user 对象 · 后续 jwt callback 写进 NextAuth cookie
 */

import NextAuth, { type DefaultSession, type User } from 'next-auth'
import Credentials from 'next-auth/providers/credentials'
import Google from 'next-auth/providers/google'

import { REWARD_COOKIE, buildRewardCookieValue } from '@/lib/reward-toast'
import { midasTradingApiFetch } from '@/lib/server/midas-trading-api'

// 仅扩展 Session / User · JWT 字段用内联 cast,避免 'next-auth/jwt' 模块增强
// 在 moduleResolution: bundler 下的解析问题
declare module 'next-auth' {
  interface Session {
    accessToken: string
    // role:刀1 后端已带(login//me/oauth)· 'admin' 才显用户管理入口(仅 UX,边界在后端 403)
    user: { id: string; email: string; role: string } & DefaultSession['user']
  }
  interface User {
    accessToken?: string
    role?: string
  }
}

type AugmentedToken = {
  accessToken?: string
  userId?: string
  email?: string
  role?: string
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: 'jwt', maxAge: 7 * 24 * 60 * 60 }, // 7d
  pages: {
    signIn: '/login',
    error: '/login',
  },
  providers: [
    Credentials({
      name: 'credentials',
      credentials: {
        email: { type: 'email' },
        password: { type: 'password' },
      },
      async authorize(credentials) {
        const email = credentials?.email as string | undefined
        const password = credentials?.password as string | undefined
        if (!email || !password) return null

        const r = await midasTradingApiFetch('/api/v1/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        if (!r.ok) {
          // 401 邮箱密码错 / 403 未验证 · 让 NextAuth UI 提示 CredentialsSignin
          return null
        }
        const data = (await r.json()) as {
          access_token: string
          user_id: string
          email: string
          role: string
        }
        const user: User = {
          id: data.user_id,
          email: data.email,
          accessToken: data.access_token,
          role: data.role,
        }
        return user
      },
    }),
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID ?? '',
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? '',
      // 防止用户首次登录被 PKCE flow 阻断;NextAuth v5 默认就是 PKCE,这里显式声明
      authorization: {
        params: {
          scope: 'openid email profile',
          prompt: 'select_account',
        },
      },
    }),
  ],
  events: {
    // 用户主动登出时,顺便通知后端 revoke DB session(0006 ADR 2026-05-21 回归)
    async signOut(message) {
      const tk = (message as { token?: { accessToken?: string } } | null)?.token
      const accessToken = tk?.accessToken
      if (!accessToken) return
      try {
        await midasTradingApiFetch('/api/v1/auth/logout', {
          method: 'POST',
          headers: { Authorization: `Bearer ${accessToken}` },
        })
      } catch {
        // 失败仅记 · 不阻塞 NextAuth 清 cookie
      }
    },
  },
  callbacks: {
    async signIn({ account }) {
      // Google OAuth 流程:拿到 Google id_token · 转发给后端换 session token
      if (account?.provider === 'google') {
        const idToken = account.id_token as string | undefined
        if (!idToken) {
          console.error('[auth.google] account.id_token 缺失 · 无法换 session · 检查 scope 是否含 openid')
          return false
        }
        console.info('[auth.google] 拿到 id_token · POST 独立 Cloudflare API 换 session')
        // Phase 1.5 刀B:OAuth ref 归因唯一路径 —— register 页落地写的 midas_ref
        // cookie 在此读出(signIn callback 是 server-side route handler · cookies()
        // 可用),进 /oauth/google body。仅 create 分支后端才兑现(刀A)。
        const { cookies } = await import('next/headers')
        const ref = (await cookies()).get('midas_ref')?.value ?? null
        try {
          const r = await midasTradingApiFetch('/api/v1/auth/oauth/google', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id_token: idToken, ref }),
          })
          if (!r.ok) {
            // 把后端返回的 detail 打出来 · 定位是验签 / DB / 网络 哪一环
            const body = await r.text().catch(() => '<no body>')
            console.error(
              '[auth.google] backend rejected · status=%d · body=%s',
              r.status,
              body.slice(0, 500),
            )
            return false
          }
          const data = (await r.json()) as {
            access_token: string
            user_id: string
            email: string
            role: string
            trial_granted?: boolean
            invite_rewarded?: boolean
          }
          // 把后端 session token + user_id 塞进 account 临时字段 ·
          // jwt() callback 会读这些字段写到 NextAuth JWT。
          // Account 类型 readonly · 强制写入用 cast 到 mutable bag
          const bag = account as unknown as Record<string, unknown>
          bag.midas_access_token = data.access_token
          bag.midas_user_id = data.user_id
          bag.midas_email = data.email
          bag.midas_role = data.role
          // Phase 1.5 刀B:OAuth 到账感知 —— 写一次性 cookie,落地 watcher
          // 读后 toast + 删(仅 create 分支后端才回 true · ref cookie 顺便清)
          const store = await cookies()
          const rewardVal = buildRewardCookieValue(
            data.trial_granted ?? false,
            data.invite_rewarded ?? false,
          )
          if (rewardVal !== null) {
            store.set(REWARD_COOKIE, rewardVal, { path: '/', maxAge: 300 })
          }
          store.delete('midas_ref')
        } catch (e) {
          console.warn('[auth.google] backend call failed:', e)
          return false
        }
      }
      return true
    },
    async jwt({ token, user, account }) {
      // ★ Google OAuth 优先:signIn callback 已把后端 session token 塞进 account(token 在 account 不在 user)。
      //   必须在 if(user) 之前判 —— OAuth 初次登录 user 也存在,但 user.accessToken 是 undefined;
      //   放后面会被 if(user) 截断、丢掉后端 token → session.accessToken 空 → 鉴权 API 401(2026-06 修)。
      if (account?.midas_access_token) {
        return {
          ...token,
          accessToken: account.midas_access_token as string,
          userId: account.midas_user_id as string,
          email: account.midas_email as string,
          role: account.midas_role as string,
        } as typeof token & AugmentedToken
      }
      // 凭据登录(邮箱/密码):authorize 把后端 session token 放进 user.accessToken
      if (user) {
        const u = user as User & { accessToken?: string }
        return {
          ...token,
          accessToken: u.accessToken,
          userId: u.id,
          email: u.email,
          role: u.role,
        } as typeof token & AugmentedToken
      }
      return token
    },
    async session({ session, token }) {
      const tk = token as typeof token & AugmentedToken
      session.accessToken = tk.accessToken ?? ''
      session.user.id = tk.userId ?? ''
      // ★ 存量 JWT(本刀上线前签发)无 role → 兜 'user':已登录用户(含 Hans)
      // 需重新登录一次才拿到 admin(JWT 只在登录时写入 · 行为如实报)
      session.user.role = tk.role ?? 'user'
      if (tk.email) session.user.email = tk.email
      return session
    },
  },
})
