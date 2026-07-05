/**
 * 详情页语义壳 · curated 品种清单(SEO 批7 · docs/seo/batch7-detail-longtail-plan.md)。
 *
 * 一份清单三用:① 路径段路由 `/{market}/[symbol]` 的 generateStaticParams(有界预渲染集)·
 * ② 语义壳的 symbol→中文名源(crypto/cn/us 无运行时静态名源 → 此处硬编码 · hk 复用 HK_POOL)·
 * ③ sitemap 扩充 + 旧 `?symbol=` curated 判定(内链/redirect)。
 *
 * ★有界:硬编码 = build 时长可控(纯静态壳无 API·见方案硬约束②)。扩容改此文件即可。
 * ★symbol 格式(与详情组件契约一致):crypto=BTCUSDT(无斜杠)· A股=纯代码 600519 ·
 *   美股=纯代码 AAPL · 港股=5 位 00700。
 * ★名称仅供语义壳展示 · 无任何 bias/方向/价格(壳是功能骨架非行情判断·见硬约束③)。
 */

import { HK_POOL } from '@/lib/hk-pool'
import type { Market } from '@midas/shared'

export interface DetailSymbol {
  symbol: string
  name: string
}

/** 加密 · 主流 USDT 永续(Binance 风格无斜杠)· 名称取通行中文名/项目名。 */
const CRYPTO_SYMBOLS: readonly DetailSymbol[] = [
  { symbol: 'BTCUSDT', name: '比特币' },
  { symbol: 'ETHUSDT', name: '以太坊' },
  { symbol: 'BNBUSDT', name: '币安币' },
  { symbol: 'SOLUSDT', name: 'Solana' },
  { symbol: 'XRPUSDT', name: '瑞波币' },
  { symbol: 'DOGEUSDT', name: '狗狗币' },
  { symbol: 'ADAUSDT', name: '艾达币' },
  { symbol: 'AVAXUSDT', name: 'Avalanche' },
  { symbol: 'TRXUSDT', name: '波场' },
  { symbol: 'LINKUSDT', name: 'Chainlink' },
  { symbol: 'DOTUSDT', name: '波卡' },
  { symbol: 'LTCUSDT', name: '莱特币' },
  { symbol: 'BCHUSDT', name: '比特币现金' },
  { symbol: 'UNIUSDT', name: 'Uniswap' },
  { symbol: 'XLMUSDT', name: '恒星币' },
  { symbol: 'ATOMUSDT', name: 'Cosmos' },
  { symbol: 'ETCUSDT', name: '以太经典' },
  { symbol: 'FILUSDT', name: 'Filecoin' },
  { symbol: 'APTUSDT', name: 'Aptos' },
  { symbol: 'ARBUSDT', name: 'Arbitrum' },
  { symbol: 'OPUSDT', name: 'Optimism' },
  { symbol: 'NEARUSDT', name: 'NEAR Protocol' },
  { symbol: 'INJUSDT', name: 'Injective' },
  { symbol: 'SUIUSDT', name: 'Sui' },
  { symbol: 'TONUSDT', name: 'Toncoin' },
  { symbol: 'SHIBUSDT', name: '柴犬币' },
  { symbol: 'PEPEUSDT', name: 'Pepe' },
  { symbol: 'WLDUSDT', name: 'Worldcoin' },
]

/** A股 · 代表性蓝筹(纯代码)。 */
const CN_SYMBOLS: readonly DetailSymbol[] = [
  { symbol: '600519', name: '贵州茅台' },
  { symbol: '601318', name: '中国平安' },
  { symbol: '600036', name: '招商银行' },
  { symbol: '000858', name: '五粮液' },
  { symbol: '300750', name: '宁德时代' },
  { symbol: '002594', name: '比亚迪' },
  { symbol: '601899', name: '紫金矿业' },
  { symbol: '600900', name: '长江电力' },
  { symbol: '600030', name: '中信证券' },
  { symbol: '000333', name: '美的集团' },
  { symbol: '600276', name: '恒瑞医药' },
  { symbol: '601166', name: '兴业银行' },
  { symbol: '600887', name: '伊利股份' },
  { symbol: '000651', name: '格力电器' },
  { symbol: '002415', name: '海康威视' },
  { symbol: '601012', name: '隆基绿能' },
  { symbol: '600028', name: '中国石化' },
  { symbol: '000001', name: '平安银行' },
]

/** 美股 · 代表性大盘(纯代码 · 无带点符号如 BRK.B 避路径边界)。 */
const US_SYMBOLS: readonly DetailSymbol[] = [
  { symbol: 'AAPL', name: '苹果' },
  { symbol: 'MSFT', name: '微软' },
  { symbol: 'NVDA', name: '英伟达' },
  { symbol: 'GOOGL', name: '谷歌' },
  { symbol: 'AMZN', name: '亚马逊' },
  { symbol: 'META', name: 'Meta' },
  { symbol: 'TSLA', name: '特斯拉' },
  { symbol: 'AVGO', name: '博通' },
  { symbol: 'JPM', name: '摩根大通' },
  { symbol: 'V', name: 'Visa' },
  { symbol: 'WMT', name: '沃尔玛' },
  { symbol: 'MA', name: '万事达' },
  { symbol: 'COST', name: '好市多' },
  { symbol: 'NFLX', name: '奈飞' },
  { symbol: 'AMD', name: 'AMD' },
  { symbol: 'KO', name: '可口可乐' },
  { symbol: 'DIS', name: '迪士尼' },
  { symbol: 'PEP', name: '百事可乐' },
]

/** 港股 · 复用现成策展池(18 只带中文名)。 */
const HK_SYMBOLS: readonly DetailSymbol[] = HK_POOL.map(({ symbol, name }) => ({ symbol, name }))

/** 市场 → curated 清单(路径段路由 / sitemap / 内链 / redirect 单一真源)。 */
export const DETAIL_SYMBOLS: Record<'crypto' | 'cn' | 'us' | 'hk', readonly DetailSymbol[]> = {
  crypto: CRYPTO_SYMBOLS,
  cn: CN_SYMBOLS,
  us: US_SYMBOLS,
  hk: HK_SYMBOLS,
}

/** 语义壳/路由支持的市场(crypto/cn/us/hk · 与 DETAIL_SYMBOLS 键一致)。 */
export const DETAIL_MARKETS = ['crypto', 'cn', 'us', 'hk'] as const
export type DetailMarket = (typeof DETAIL_MARKETS)[number]

/** 是否 detail 语义壳支持的市场(narrowing)。 */
export function isDetailMarket(m: string): m is DetailMarket {
  return (DETAIL_MARKETS as readonly string[]).includes(m)
}

/** 某市场某 symbol 是否 curated(内链导向 + 旧 URL redirect 判定)。 */
export function isCuratedSymbol(market: Market, symbol: string): boolean {
  if (!isDetailMarket(market)) return false
  const s = symbol.trim().toUpperCase()
  return DETAIL_SYMBOLS[market].some((it) => it.symbol.toUpperCase() === s)
}

/** 取 curated 名称(语义壳 · 大小写不敏感);非 curated 返 undefined。 */
export function getCuratedName(market: DetailMarket, symbol: string): string | undefined {
  const s = symbol.trim().toUpperCase()
  return DETAIL_SYMBOLS[market].find((it) => it.symbol.toUpperCase() === s)?.name
}

/**
 * 品种 → 详情页链接(SEO 批7 · 内链消费方统一走此)。
 *  - curated → 路径段 `/{market}/{SYMBOL}`(SEO 页 · 静态壳 · 大写规整化对齐 generateStaticParams)。
 *  - 非 curated → 旧 query `/{market}-preview?symbol=...`(&name= 兜底 · 现状不变)。
 * ★curated symbol 全为大写/数字 → toUpperCase() 即 generateStaticParams 的规范形态(避免大小写 404)。
 */
export function detailHref(item: { symbol: string; market: Market; name?: string }): string {
  const { symbol, market, name } = item
  if (isDetailMarket(market) && isCuratedSymbol(market, symbol)) {
    return `/${market}/${encodeURIComponent(symbol.trim().toUpperCase())}`
  }
  const s = encodeURIComponent(symbol)
  if (market === 'crypto') return `/crypto-preview?symbol=${s}`
  const n = name ? `&name=${encodeURIComponent(name)}` : ''
  return `/${market}-preview?symbol=${s}${n}`
}
