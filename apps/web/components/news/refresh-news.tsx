'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useTransition } from 'react'

export function RefreshNews({ english }: { english: boolean }) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') router.refresh()
    }, 15 * 60_000)
    return () => window.clearInterval(timer)
  }, [router])
  return <button type="button" disabled={pending} onClick={() => startTransition(() => router.refresh())}
    className="text-xs text-muted-foreground underline underline-offset-4 hover:text-midas-red">
    {pending ? (english ? 'Refreshing…' : '刷新中…') : (english ? 'Refresh' : '刷新')}
  </button>
}
