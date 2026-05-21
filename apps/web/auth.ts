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

const API_BASE = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// 仅扩展 Session / User · JWT 字段用内联 cast,避免 'next-auth/jwt' 模块增强
// 在 moduleResolution: bundler 下的解析问题
declare module 'next-auth' {
  interface Session {
    accessToken: string
    user: { id: string; email: string } & DefaultSession['user']
  }
  interface User {
    accessToken?: string
  }
}

type AugmentedToken = {
  accessToken?: string
  userId?: string
  email?: string
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

        const r = await fetch(`${API_BASE}/api/v1/auth/login`, {
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
        }
        const user: User = {
          id: data.user_id,
          email: data.email,
          accessToken: data.access_token,
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
        await fetch(`${API_BASE}/api/v1/auth/logout`, {
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
        if (!idToken) return false
        try {
          const r = await fetch(`${API_BASE}/api/v1/auth/oauth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id_token: idToken }),
          })
          if (!r.ok) {
            console.warn(
              '[auth.google] backend rejected · status=%d',
              r.status,
            )
            return false
          }
          const data = (await r.json()) as {
            access_token: string
            user_id: string
            email: string
          }
          // 把后端 session token + user_id 塞进 account 临时字段 ·
          // jwt() callback 会读这些字段写到 NextAuth JWT。
          // Account 类型 readonly · 强制写入用 cast 到 mutable bag
          const bag = account as unknown as Record<string, unknown>
          bag.midas_access_token = data.access_token
          bag.midas_user_id = data.user_id
          bag.midas_email = data.email
        } catch (e) {
          console.warn('[auth.google] backend call failed:', e)
          return false
        }
      }
      return true
    },
    async jwt({ token, user, account }) {
      // 第一次登录(Credentials):把后端 session token + user_id + email 塞进 NextAuth JWT
      if (user) {
        const u = user as User & { accessToken?: string }
        return {
          ...token,
          accessToken: u.accessToken,
          userId: u.id,
          email: u.email,
        } as typeof token & AugmentedToken
      }
      // Google OAuth · signIn callback 已经把 backend session 塞到 account 里
      if (account?.midas_access_token) {
        return {
          ...token,
          accessToken: account.midas_access_token as string,
          userId: account.midas_user_id as string,
          email: account.midas_email as string,
        } as typeof token & AugmentedToken
      }
      return token
    },
    async session({ session, token }) {
      const tk = token as typeof token & AugmentedToken
      session.accessToken = tk.accessToken ?? ''
      session.user.id = tk.userId ?? ''
      if (tk.email) session.user.email = tk.email
      return session
    },
  },
})
