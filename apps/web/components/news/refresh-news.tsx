'use client'

import { RefreshCw } from 'lucide-react'
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
    className="ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-surface-subtle hover:text-foreground focus-visible:outline-midas-red disabled:opacity-60">
    <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
    {pending ? (english ? 'Refreshing…' : '刷新中…') : (english ? 'Refresh' : '刷新')}
  </button>
}

// A streamed route can resolve its fragment before the new headlines reach the DOM.
export function NewsReadingPosition({ endPage }: { endPage: number }) {
  useEffect(() => {
    if (!location.hash.startsWith('#headline-')) return
    const row = Array.from(document.querySelectorAll<HTMLLIElement>('li[id^="headline-"]'))
      .find(item => '#' + encodeURIComponent(item.id) === location.hash)
    if (row) {
      row.scrollIntoView({ block: 'start' })
      row.querySelector<HTMLAnchorElement>('h3 a')?.focus({ preventScroll: true })
    }
  }, [endPage])
  return null
}
