'use client'

export const dynamic = 'force-dynamic'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useRef, useState } from 'react'

import { AuthShell } from '@/components/auth/auth-shell'
import { Button } from '@/components/ui/button'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type State =
  | { status: 'loading' }
  | { status: 'success'; email: string }
  | { status: 'error'; detail: string }

function VerifyEmailInner() {
  const params = useSearchParams()
  const token = params.get('token')
  const [state, setState] = useState<State>({ status: 'loading' })
  const calledRef = useRef(false)

  useEffect(() => {
    if (calledRef.current) return
    calledRef.current = true
    if (!token) {
      setState({ status: 'error', detail: '验证链接缺少 token' })
      return
    }
    void (async () => {
      try {
        const r = await fetch(`${API_BASE}/api/v1/auth/verify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
        })
        if (!r.ok) {
          const body = (await r.json().catch(() => null)) as { detail?: string } | null
          setState({
            status: 'error',
            detail: body?.detail ?? `验证失败:HTTP ${r.status}`,
          })
          return
        }
        const data = (await r.json()) as { email: string }
        setState({ status: 'success', email: data.email })
      } catch (e) {
        setState({ status: 'error', detail: `网络错误:${(e as Error).message}` })
      }
    })()
  }, [token])

  if (state.status === 'loading') {
    return (
      <AuthShell title="验证中…" subtitle="正在确认邮箱链接,请稍候">
        <p className="text-sm text-muted-foreground">如果停留时间过长,请刷新本页。</p>
      </AuthShell>
    )
  }

  if (state.status === 'success') {
    return (
      <AuthShell
        title="邮箱验证成功"
        subtitle={`${state.email} 已确认。现在可以登录。`}
      >
        <Link href="/login">
          <Button className="w-full" size="lg">
            前往登录
          </Button>
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="验证失败" subtitle={state.detail}>
      <div className="space-y-3">
        <Link href="/login">
          <Button variant="outline" className="w-full">
            到登录页重发验证邮件
          </Button>
        </Link>
        <p className="text-xs text-muted-foreground/70">
          如长期收不到邮件 / token 一直过期,请联系客服。
        </p>
      </div>
    </AuthShell>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<AuthShell title="载入中…">{null}</AuthShell>}>
      <VerifyEmailInner />
    </Suspense>
  )
}
