/**
 * 训练营文章 →「去实战练」入口配置 · 纯数据(可逐篇增量)。
 *
 * 每篇可选配一个实战入口:跳对应市场详情页或工作台(/workbench · 无 symbol)。
 * buildPracticeHref 统一拼路由;getPractice 取某篇配置(无 → null,不渲染入口)。
 * 详情链接复用站内统一规则:策展品种走语义路径,长尾走查询参数。
 *
 * 目标路由均匿名可访问、不接真实交易(CLAUDE.md 红线:点金永远只用虚拟资金)。
 */

import { detailHref } from '@/lib/seo/detail-symbols'
import type { Market } from '@midas/shared'

export type PracticeMarket = Market | 'workbench'

export interface PracticeEntry {
  market: PracticeMarket
  /** 标的代码(crypto: BTCUSDT · A股: 600519 · 美股: NVDA · 港股: 00700)· workbench 无需 */
  symbol?: string
  /** 按钮副文案(引导去做什么) */
  label: string
}

/** 市场 → 详情页路由(workbench 无 symbol) */
const MARKET_ROUTE: Record<PracticeMarket, string> = {
  crypto: '/crypto-preview',
  cn: '/cn-preview',
  us: '/us-preview',
  hk: '/hk-preview',
  workbench: '/workbench',
}

/** 拼实战入口 href:有 symbol → ?symbol=xxx;workbench / 无 symbol → 裸路由。 */
export function buildPracticeHref(entry: PracticeEntry): string {
  const base = MARKET_ROUTE[entry.market]
  if (entry.market === 'workbench' || !entry.symbol) return base
  return detailHref({ market: entry.market, symbol: entry.symbol })
}

/**
 * 文章 slug → 实战入口配置(可逐篇增量补充;此处先放样例验证机制)。
 * 内容由产品方后续提供。
 */
export const ACADEMY_PRACTICE: Record<string, PracticeEntry> = {
  A2: { market: 'crypto', symbol: 'BTCUSDT', label: '打开 BTC 行情,对照 K 线的四价与阴阳线' },
  A3: { market: 'crypto', symbol: 'BTCUSDT', label: '在 BTC K 线上找找带长上影 / 长下影的蜡烛' },
  B1: { market: 'cn', symbol: '600519', label: '在贵州茅台日线上叠加均线,观察趋势与金叉死叉' },
}

/** 取某篇的实战入口配置(无 → null → 不渲染入口) */
export function getPractice(slug: string): PracticeEntry | null {
  return ACADEMY_PRACTICE[slug] ?? null
}
