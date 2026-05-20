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
  const nextPath = params.get('next') ?? '/workbench'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

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

        <Button type="submit" className="w-full" size="lg" disabled={busy}>
          {busy ? '登录中…' : '登录'}
        </Button>
      </form>
    </AuthShell>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={<AuthShell title="加载中…">{null}</AuthShell>}>
      <LoginInner />
    </Suspense>
  )
}
