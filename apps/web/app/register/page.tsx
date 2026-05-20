'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { AuthShell } from '@/components/auth/auth-shell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export default function RegisterPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [ageOk, setAgeOk] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [success, setSuccess] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    if (!ageOk) {
      setError('必须确认年满 18 周岁')
      return
    }
    if (password.length < 8) {
      setError('密码至少 8 个字符')
      return
    }
    setBusy(true)
    try {
      const r = await fetch(`${API_BASE}/api/v1/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, age_confirmed: true }),
      })
      if (!r.ok) {
        const body = (await r.json().catch(() => null)) as { detail?: string } | null
        setError(body?.detail ?? `注册失败:HTTP ${r.status}`)
        return
      }
      setSuccess('注册成功!验证邮件已发送到你的邮箱,点击邮件中链接完成验证后即可登录。')
    } finally {
      setBusy(false)
    }
  }

  if (success) {
    return (
      <AuthShell
        title="请查收邮件"
        subtitle="验证链接 24 小时内有效"
        footer={
          <span className="text-muted-foreground">
            没收到邮件?
            <button
              type="button"
              className="ml-1 text-midas-red hover:underline"
              onClick={() => router.push(`/login?email=${encodeURIComponent(email)}`)}
            >
              到登录页重发
            </button>
          </span>
        }
      >
        <p className="text-sm text-foreground leading-relaxed">{success}</p>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="注册"
      subtitle="创建账号,免费跨市场分析"
      footer={
        <span className="text-muted-foreground">
          已有账号?
          <Link href="/login" className="ml-1 text-midas-red hover:underline">
            登录
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
            密码(至少 8 位)
          </label>
          <Input
            id="password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <label className="flex items-start gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 accent-midas-red"
            checked={ageOk}
            onChange={(e) => setAgeOk(e.target.checked)}
          />
          <span>
            我已年满 <strong>18 周岁</strong>,知悉点金 Midas 是模拟交易终端,
            提供的所有信息不构成投资建议。
          </span>
        </label>

        {error && (
          <p className="rounded-md bg-midas-red-glow px-3 py-2 text-sm text-midas-red">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" size="lg" disabled={busy}>
          {busy ? '提交中…' : '注册并发送验证邮件'}
        </Button>
      </form>
    </AuthShell>
  )
}
