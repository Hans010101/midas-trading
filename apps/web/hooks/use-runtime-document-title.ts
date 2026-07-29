'use client'

import { useEffect } from 'react'

export function useRuntimeDocumentTitle({
  locale,
  english,
  chinese,
}: {
  locale: 'en' | 'zh'
  english: string
  chinese: string
}) {
  useEffect(() => {
    const title = locale === 'en'
      ? `${english} · Midas Trading`
      : `${chinese} · 点金 Midas`
    document.title = title

    const observer = new MutationObserver(() => {
      if (document.title !== title) document.title = title
    })
    observer.observe(document.head, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [chinese, english, locale])
}
