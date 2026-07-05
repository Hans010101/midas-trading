'use client'

/**
 * 旧 `?symbol=` → 路径段静态壳的 client 兜底重定向(SEO 批7)。
 *
 * 挂在 4 个 `/{market}-preview` 页(Suspense 内)· 读 ?symbol=,若是 curated symbol →
 * `router.replace` 到 `/{market}/{SYMBOL}`(路径段 SEO 页)。非 curated → 不动(长尾仍留旧页)。
 * ★只在旧 -preview 页挂(路径段页不挂)· 无循环。渲染 null · 不改 -preview 页的静态属性。
 * 覆盖 Cmd+K / 外链 / 书签 等所有到旧 curated URL 的入口(内链已切 detailHref,此为兜底)。
 */

import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect } from 'react'

import { isCuratedSymbol } from '@/lib/seo/detail-symbols'
import type { Market } from '@midas/shared'

export function CuratedRedirect({ market }: { market: Market }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const symbol = (searchParams.get('symbol') ?? '').trim()

  useEffect(() => {
    if (symbol && isCuratedSymbol(market, symbol)) {
      router.replace(`/${market}/${encodeURIComponent(symbol.toUpperCase())}`)
    }
  }, [market, symbol, router])

  return null
}
