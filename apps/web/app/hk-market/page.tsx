/**
 * 港股市场首页 · /hk-market(港股首页全市场 · 单元2)。
 *
 * 对标 A股/美股 MarketHomePage:市场状态 + 大盘指数卡(恒生 + 恒生国企)+ 涨跌家数情绪条 +
 * 涨幅/跌幅/成交额榜(见 HkSections)。
 * ★★ 标注「主要成分股 / 活跃精选」· 绝不写「全市场」(新浪限页 ~900 只主要成分 · 非 2764 全市场)。
 * 阶段二的 18 只简化列表 → 升级为本完整首页(榜单吸收列表)。
 * ★ 港股只读:不下单、不接 AI(阶段三)。红线:仅虚拟资金。
 */

import type { Metadata } from 'next'

import { MarketHomePage } from '@/components/market-home/market-home-page'

// SEO 批3:市场页独立 metadata · 短 title 由 layout 模板补「· 点金 Midas」。
export const metadata: Metadata = {
  title: '港股行情',
  description:
    '港股行情:恒生指数、恒生国企指数与主要成分股涨跌、成交额榜单。行情数据仅供参考,不构成投资建议。',
  alternates: { canonical: '/hk-market' },
  openGraph: {
    title: '港股行情 · 点金 Midas',
    description: '港股:恒生指数、国企指数、主要成分股涨跌与成交额榜。数据仅供参考。',
    url: '/hk-market',
  },
}

export default function HkMarketPage() {
  return <MarketHomePage market="hk" />
}
