/**
 * 加密品种详情 · 路径段语义壳(SEO 批7)· /crypto/[symbol]。
 *
 * 纯静态(generateStaticParams 有界 curated 集 + dynamicParams=false)· 爬虫看 Suspense
 * fallback = DetailSeoShell(server 静态语义内容)· 用户端 CryptoDetail hydrate 后替换。
 * 非 curated symbol → 404(长尾仍走旧 /crypto-preview?symbol=)。
 */

import { Suspense } from 'react'

import type { Metadata } from 'next'

import { CryptoDetail } from '@/components/crypto-preview/crypto-detail'
import { DetailSeoShell } from '@/components/seo/detail-seo-shell'
import { DETAIL_SYMBOLS, getCuratedName } from '@/lib/seo/detail-symbols'

export function generateStaticParams() {
  return DETAIL_SYMBOLS.crypto.map((s) => ({ symbol: s.symbol }))
}

export const dynamicParams = false

export async function generateMetadata({
  params,
}: {
  params: Promise<{ symbol: string }>
}): Promise<Metadata> {
  const { symbol } = await params
  const name = getCuratedName('crypto', symbol) ?? symbol
  const title = `${name}（${symbol}）· 加密货币行情与技术分析`
  const description = `${name}（${symbol}）永续合约的多周期 K 线、技术指标（均线/MACD/RSI/布林）与资金费率、持仓量、多空比等合约数据分析。配虚拟交易沙盘，仅供参考，不构成投资建议。`
  const canonical = `/crypto/${symbol}`
  return {
    title,
    description,
    alternates: { canonical },
    openGraph: { title, description, url: canonical },
  }
}

export default async function CryptoSymbolPage({
  params,
}: {
  params: Promise<{ symbol: string }>
}) {
  const { symbol } = await params
  const name = getCuratedName('crypto', symbol) ?? symbol
  return (
    <Suspense fallback={<DetailSeoShell market="crypto" symbol={symbol} name={name} />}>
      <CryptoDetail symbol={symbol} />
    </Suspense>
  )
}
