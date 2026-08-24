'use client'

export const dynamic = 'force-dynamic'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { signIn } from 'next-auth/react'
import { Suspense, useState } from 'react'

import { AuthShell } from '@/components/auth/auth-shell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

function LoginInner() {
  const router = useRouter()
  const params = useSearchParams()
  const nextPath = params.get('next') ?? '/global'
  const [email, setEmail] = useState(() => params.get('email') ?? '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [resendNotice, setResendNotice] = useState<string | null>(null)

  async function resendVerification() {
    if (!email) {
      setError('请先填写邮箱')
      return
    }
    setBusy(true)
    setError(null)
    setResendNotice(null)
    try {
      const r = await fetch('/api-proxy/api/v1/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (!r.ok) {
        const body = (await r.json().catch(() => null)) as { detail?: string } | null
        setError(body?.detail ?? `发送失败:HTTP ${r.status}`)
        return
      }
      setResendNotice('如果该邮箱尚未验证，验证邮件已重新发送。')
    } catch {
      setError('网络异常，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const result = await signIn('credentials', {
      email,
      password,
      redirect: false,
    })
    setBusy(false)
    if (result?.error) {
      setError('邮箱或密码错误,或邮箱尚未验证')
      return
    }
    router.push(nextPath)
    router.refresh()
  }

  return (
    <AuthShell
      title="登录"
      subtitle="登录以进入跨市场分析终端"
      footer={
        <span className="text-muted-foreground">
          还没账号?
          <Link href="/register" className="ml-1 text-midas-red hover:underline">
            注册
          </Link>
        </span>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="email" className="text-sm font-medium text-foreground">
            邮箱
          </label>
          <Input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <label htmlFor="password" className="text-sm font-medium text-foreground">
            密码
          </label>
          <Input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && (
          <p className="rounded-md bg-midas-red-glow px-3 py-2 text-sm text-midas-red">
            {error}
          </p>
        )}
        {resendNotice && (
          <p className="text-sm text-foreground">{resendNotice}</p>
        )}

        <Button type="submit" className="w-full" size="lg" disabled={busy}>
          {busy ? '登录中…' : '登录'}
        </Button>
        <button
          type="button"
          className="w-full text-sm text-midas-red hover:underline disabled:opacity-50"
          disabled={busy}
          onClick={resendVerification}
        >
          邮箱未验证或没收到邮件？重新发送验证邮件
        </button>
      </form>

      {/* 分隔线 + Google OAuth(M1 第三波 · 邮箱密码保留并存)*/}
      <div className="relative my-5 flex items-center">
        <div className="flex-1 border-t border-paper" />
        <span className="px-3 text-xs text-muted-foreground">或</span>
        <div className="flex-1 border-t border-paper" />
      </div>
      <Button
        type="button"
        variant="outline"
        className="w-full"
        size="lg"
        disabled={busy}
        onClick={() => {
          // NextAuth Google provider · redirect 到 Google 同意页 ·
          // 回来后通过 signIn callback 调后端 /oauth/google 换 session
          void signIn('google', { callbackUrl: nextPath })
        }}
      >
        <GoogleIcon /> Google 登录
      </Button>
    </AuthShell>
  )
}


function GoogleIcon() {
  return (
    <svg
      className="mr-2 h-4 w-4"
      viewBox="0 0 18 18"
      aria-hidden
    >
      <path
        d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"
        fill="#4285F4"
      />
      <path
        d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
        fill="#34A853"
      />
      <path
        d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.04l3.007-2.333z"
        fill="#FBBC05"
      />
      <path
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.96L3.964 7.293C4.672 5.166 6.656 3.58 9 3.58z"
        fill="#EA4335"
      />
    </svg>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={<AuthShell title="载入中…">{null}</AuthShell>}>
      <LoginInner />
    </Suspense>
  )
}
