/**
 * A股个股详情 · 路径段语义壳(SEO 批7)· /cn/[symbol]。
 * 纯静态(curated 有界 + dynamicParams=false)· 爬虫看 DetailSeoShell · 非 curated → 404
 * (长尾仍走旧 /cn-preview?symbol=)。SpotDetail 收 symbol+name prop(免依赖 ?name=)。
 */

import { Suspense } from 'react'

import type { Metadata } from 'next'

import { DetailSeoShell } from '@/components/seo/detail-seo-shell'
import { SpotDetail } from '@/components/spot-preview/spot-detail'
import { DETAIL_SYMBOLS, getCuratedName } from '@/lib/seo/detail-symbols'

export function generateStaticParams() {
  return DETAIL_SYMBOLS.cn.map((s) => ({ symbol: s.symbol }))
}

export const dynamicParams = false

export async function generateMetadata({
  params,
}: {
  params: Promise<{ symbol: string }>
}): Promise<Metadata> {
  const { symbol } = await params
  const name = getCuratedName('cn', symbol) ?? symbol
  const title = `${name}（${symbol}）· A股行情与技术分析`
  const description = `A股 ${name}（${symbol}）的多周期 K 线、技术指标（均线/MACD/RSI/布林）与技术面客观结构诊断。配虚拟交易沙盘，仅供参考，不构成投资建议。`
  const canonical = `/cn/${symbol}`
  return {
    title,
    description,
    alternates: { canonical },
    openGraph: { title, description, url: canonical },
  }
}

export default async function CnSymbolPage({
  params,
}: {
  params: Promise<{ symbol: string }>
}) {
  const { symbol } = await params
  const name = getCuratedName('cn', symbol) ?? symbol
  return (
    <Suspense fallback={<DetailSeoShell market="cn" symbol={symbol} name={name} />}>
      <SpotDetail market="cn" symbol={symbol} name={name} />
    </Suspense>
  )
}
