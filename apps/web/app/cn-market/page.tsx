import type { Metadata } from 'next'

import { MarketHomePage } from '@/components/market-home/market-home-page'

// SEO 批3:市场页独立 metadata(此前吃全站模板)· 短 title 由 layout 模板补「· 点金 Midas」。
export const metadata: Metadata = {
  title: 'A 股行情',
  description:
    'A 股沪深全市场行情:实时大盘指数、涨跌家数、成交额与行业板块热力图榜单。',
  alternates: { canonical: '/cn-market' },
  openGraph: {
    title: 'A 股行情 · 点金 Midas',
    description: 'A 股沪深全市场:指数、涨跌家数、成交额与行业板块榜单。',
    url: '/cn-market',
  },
}

/** A股市场首页(0023 阶段③ · 3.1)· /cn-market · 类比 /crypto-market。 */
export default function CnMarketPage() {
  return <MarketHomePage market="cn" />
}
