import type { Metadata } from 'next'
import { cookies } from 'next/headers'

import { MarketHomePage } from '@/components/market-home/market-home-page'
import { LOCALE_COOKIE } from '@/i18n/routing'

// SEO 批3:市场页独立 metadata(此前吃全站模板)· 短 title 由 layout 模板补「· 点金 Midas」。
export async function generateMetadata(): Promise<Metadata> {
  const english = (await cookies()).get(LOCALE_COOKIE)?.value === 'en'
  const title = english ? 'A-shares' : 'A 股行情'
  const description = english
    ? 'Mainland China market indices, breadth, turnover, sector heatmaps and curated A-share rankings.'
    : 'A 股沪深全市场行情:实时大盘指数、涨跌家数、成交额与行业板块热力图榜单。'
  return {
    title: {
      absolute: english ? `${title} · Midas Trading` : `${title} · 点金 Midas`,
    },
    description,
    alternates: { canonical: '/cn-market' },
    openGraph: {
      title: english ? `${title} · Midas Trading` : `${title} · 点金 Midas`,
      description,
      url: '/cn-market',
    },
  }
}

/** A股市场首页(0023 阶段③ · 3.1)· /cn-market · 类比 /crypto-market。 */
export default function CnMarketPage() {
  return <MarketHomePage market="cn" />
}
