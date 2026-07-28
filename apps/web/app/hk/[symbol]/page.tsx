/**
 * 港股个股详情 · 路径段语义壳(SEO 批7)· /hk/[symbol]。
 * 纯静态(curated=HK_POOL 18 只 + dynamicParams=false)· 爬虫看 DetailSeoShell · 非 curated → 404
 * (长尾仍走旧 /hk-preview?symbol=)。港股只读(SpotDetail market='hk' 内部 gate 掉 AI/下单)。
 */

import { Suspense } from 'react'

import type { Metadata } from 'next'

import { DetailSeoShell } from '@/components/seo/detail-seo-shell'
import { SpotDetail } from '@/components/spot-preview/spot-detail'
import { DETAIL_SYMBOLS, getCuratedName } from '@/lib/seo/detail-symbols'

export function generateStaticParams() {
  return DETAIL_SYMBOLS.hk.map((s) => ({ symbol: s.symbol }))
}

export const dynamicParams = false

export async function generateMetadata({
  params,
}: {
  params: Promise<{ symbol: string }>
}): Promise<Metadata> {
  const { symbol } = await params
  const name = getCuratedName('hk', symbol) ?? symbol
  const title = `${name}（${symbol}）· 港股行情与技术分析`
  const description = `港股 ${name}（${symbol}）的多周期 K 线、技术指标（均线/MACD/RSI/布林）与技术面客观结构诊断。`
  const canonical = `/hk/${symbol}`
  return {
    title,
    description,
    alternates: { canonical },
    openGraph: { title, description, url: canonical },
  }
}

export default async function HkSymbolPage({
  params,
}: {
  params: Promise<{ symbol: string }>
}) {
  const { symbol } = await params
  const name = getCuratedName('hk', symbol) ?? symbol
  return (
    <Suspense fallback={<DetailSeoShell market="hk" symbol={symbol} name={name} />}>
      <SpotDetail market="hk" symbol={symbol} name={name} />
    </Suspense>
  )
}
