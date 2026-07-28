import type { Metadata } from 'next'

import { MarketHomePage } from '@/components/market-home/market-home-page'

// SEO 批3:市场页独立 metadata · 短 title 由 layout 模板补「· 点金 Midas」。
export const metadata: Metadata = {
  title: '美股行情',
  description:
    '美股行情:纳斯达克、纽交所实时指数、涨跌排行与成交额榜单,后复权口径透明。',
  alternates: { canonical: '/us-market' },
  openGraph: {
    title: '美股行情 · 点金 Midas',
    description: '美股:纳斯达克/NYSE 指数、涨跌排行、成交额榜。',
    url: '/us-market',
  },
}

/** 美股市场首页(0023 阶段③ · 3.1)· /us-market · 类比 /crypto-market。 */
export default function UsMarketPage() {
  return <MarketHomePage market="us" />
}
