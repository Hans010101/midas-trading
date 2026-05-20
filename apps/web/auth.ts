/**
 * NextAuth v5(Auth.js)配置。
 *
 * 用 CredentialsProvider 调后端 /api/v1/auth/login,JWT session strategy(0006 ADR)。
 * Backend 已经在 Bearer JWT 里携带 user_id,前端只 cookie 这一层 NextAuth 来管。
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
