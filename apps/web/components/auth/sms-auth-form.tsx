'use client'

import { useRouter } from 'next/navigation'
import { signIn } from 'next-auth/react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function SmsAuthForm({
  mode,
  nextPath = '/global',
}: {
  mode: 'login' | 'register'
  nextPath?: string
}) {
  const router = useRouter()
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [ageOk, setAgeOk] = useState(false)
  const [busy, setBusy] = useState(false)
  const [cooldown, setCooldown] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!cooldown) return
    const timer = window.setTimeout(() => setCooldown(false), 60_000)
    return () => window.clearTimeout(timer)
  }, [cooldown])

  async function requestCode() {
    setBusy(true)
    setError(null)
    try {
      const response = await fetch('/api-proxy/api/v1/auth/sms/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      })
      const body = (await response.json().catch(() => null)) as
        | { detail?: string }
        | null
      if (!response.ok) {
        setError(body?.detail ?? '验证码发送失败，请稍后重试')
        return
      }
      setCooldown(true)
    } catch {
      setError('网络异常，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (mode === 'register' && !ageOk) {
      setError('必须确认年满 18 周岁')
      return
    }
    setBusy(true)
    setError(null)
    const result = await signIn('credentials', {
      mode: 'sms',
      phone,
      code,
      create: String(mode === 'register'),
      age_confirmed: String(ageOk),
      redirect: false,
    })
    setBusy(false)
    if (result?.error) {
      setError(
        mode === 'login'
          ? '验证码错误、已过期，或该手机号尚未注册'
          : '验证码错误或已过期',
      )
      return
    }
    router.push(nextPath)
    router.refresh()
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-2">
        <label htmlFor={`${mode}-phone`} className="text-sm font-medium text-foreground">
          手机号
        </label>
        <Input
          id={`${mode}-phone`}
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="中国大陆手机号"
          required
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
        />
      </div>
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1 space-y-2">
          <label htmlFor={`${mode}-code`} className="text-sm font-medium text-foreground">
            验证码
          </label>
          <Input
            id={`${mode}-code`}
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            required
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/gu, ''))}
          />
        </div>
        <Button
          type="button"
          variant="outline"
          disabled={busy || cooldown || phone.trim().length < 11}
          onClick={requestCode}
        >
          {cooldown ? '60 秒后重发' : '发送验证码'}
        </Button>
      </div>
      {mode === 'register' && (
        <label className="flex items-start gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 accent-midas-red"
            checked={ageOk}
            onChange={(event) => setAgeOk(event.target.checked)}
          />
          <span>我已年满 <strong>18 周岁</strong></span>
        </label>
      )}
      {error && (
        <p className="rounded-md bg-midas-red-glow px-3 py-2 text-sm text-midas-red">
          {error}
        </p>
      )}
      <Button type="submit" className="w-full" size="lg" disabled={busy}>
        {busy ? '处理中…' : mode === 'login' ? '短信登录' : '手机注册并登录'}
      </Button>
    </form>
  )
}
