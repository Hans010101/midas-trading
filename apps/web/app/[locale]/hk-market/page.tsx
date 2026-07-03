/**
 * 港股市场首页 · /hk-market(港股首页全市场 · 单元2)。
 *
 * 对标 A股/美股 MarketHomePage:市场状态 + 大盘指数卡(恒生 + 恒生国企)+ 涨跌家数情绪条 +
 * 涨幅/跌幅/成交额榜(见 HkSections)。
 * ★★ 标注「主要成分股 / 活跃精选」· 绝不写「全市场」(新浪限页 ~900 只主要成分 · 非 2764 全市场)。
 * 阶段二的 18 只简化列表 → 升级为本完整首页(榜单吸收列表)。
 * ★ 港股只读:不下单、不接 AI(阶段三)。红线:仅虚拟资金。
 */

import { MarketHomePage } from '@/components/market-home/market-home-page'

export default function HkMarketPage() {
  return <MarketHomePage market="hk" />
}
