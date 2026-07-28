/**
 * 全局命令面板(Cmd+K)· 纯导航逻辑(品种→详情路由 + 功能页 + 市场次序)。
 *
 * 抽成纯模块便于 vitest 单测(不拉 cmdk / Radix / hooks)· 组件 command-palette.tsx import 之。
 * ★零 [id]:品种跳转一律 ?symbol= 查询参数(crypto 无 name · cn/us/hk 带可选 name)。
 */

import type { Market } from '@midas/shared'

// 四市场显示次序(★含 hk —— 原 workbench symbol-search-dialog 的 MARKET_ORDER 漏了 hk,泛化时补齐)
export const MARKET_ORDER: readonly Market[] = ['crypto', 'us', 'cn', 'hk']

/**
 * 品种 → 详情页路由(*-preview?symbol=)。
 *  - crypto → /crypto-preview?symbol=BTCUSDT(crypto-detail 自行派生,不传 name)
 *  - cn/us/hk → /{m}-preview?symbol=XXX&name=YYY(name 可选;spot-detail 读 ?name= 兜底)
 */
export function symbolHref(item: { symbol: string; market: Market; name?: string }): string {
  const s = encodeURIComponent(item.symbol)
  if (item.market === 'crypto') return `/crypto-preview?symbol=${s}`
  const n = item.name ? `&name=${encodeURIComponent(item.name)}` : ''
  return `/${item.market}-preview?symbol=${s}${n}`
}

export interface FuncPage {
  label: string
  href: string
  hint: string
}

/** 功能页快速跳转(★不含训练营 —— 系统性学习模块,不适合快速跳)· 路由均已核实存在 */
export const FUNC_PAGES: readonly FuncPage[] = [
  { label: '终端', href: '/workbench', hint: '工作台' },
  { label: '策略研究室', href: '/lab/assistant', hint: '沙盘 + 回测' },
  { label: '个人中心', href: '/account/membership', hint: '账户信息' },
  { label: '自选', href: '/watchlist', hint: '自选汇总' },
  { label: '财经日历', href: '/calendar', hint: '宏观事件日程' },
]
