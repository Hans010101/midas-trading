/**
 * NextAuth v5(Auth.js)配置。
 *
 * 用 CredentialsProvider 调后端 /api/v1/auth/login,JWT session strategy(NextAuth 自己的 cookie · 不是后端 JWT)。
 *
 * 0006 ADR 2026-05-21 回归后:
 *   - 后端 /login 返回 `access_token` 字段仍是这个名字,但内容已从 JWT 改成
 *     **opaque DB session token**(7 天滚动 TTL + 单用户 5 设备上限)。
 *   - 前端 NextAuth 把它当 opaque 字符串塞进自己的 cookie · 调用方无感。
 *   - Authorization: Bearer <token> 给后端 · 后端走 verify_session 查 DB · 现有 JWT 用户自然失效需要重登。
 */

import NextAuth, { type DefaultSession, type User } from 'next-auth'
import Credentials from 'next-auth/providers/credentials'

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
    async jwt({ token, user }) {
      // 第一次登录:把后端 JWT + user_id + email 塞进 NextAuth JWT
      if (user) {
        const u = user as User & { accessToken?: string }
        return {
          ...token,
          accessToken: u.accessToken,
          userId: u.id,
          email: u.email,
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
