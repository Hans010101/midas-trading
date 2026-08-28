'use client'

import { useEffect } from 'react'

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => console.error(error), [error])

  return (
    <main className="flex min-h-[70vh] items-center justify-center bg-background px-4 text-foreground">
      <div className="max-w-md rounded-xl border border-paper bg-cream p-7 text-center shadow-sm">
        <p className="font-serif text-lg font-bold">页面暂时无法载入</p>
        <p className="mt-2 text-sm text-muted-foreground">
          请检查网络后重试。你的自选和账户数据不会受影响。
        </p>
        <p className="mt-1 text-xs text-muted-foreground/70">
          This page could not load. Your saved data is safe.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-5 rounded-md bg-midas-red px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          重新载入 / Retry
        </button>
      </div>
    </main>
  )
}
