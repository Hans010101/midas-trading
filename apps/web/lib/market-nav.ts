/**
 * 顶部市场导航高亮判定(修复刀:/account 域误亮"加密")· 纯函数 vitest 可测。
 *
 * 原 bug:active = homeMarket ?? detailMarket ?? storeMarket —— workbench store
 * 残留值(默认 crypto)在所有"未豁免"页面兜底误亮;global/watchlist/lab 是
 * 逐页打的豁免补丁,/account 域没加 = 第 4 次同类 bug。
 * 治本:反转为白名单 —— store 兜底【只在 /workbench】生效(它是唯一页内切换
 * 不变 URL、必须靠 store 高亮的页面);其余路径不属于已知市场路由 → null 全不亮。
 * 未来任何新中性页(用户中心/登录/…)天然不亮,无需再加豁免。
 */

import type { Market } from '@midas/shared'

export function homeMarketOf(pathname: string | null): Market | null {
  if (!pathname) return null
  if (pathname.startsWith('/cn-market')) return 'cn'
  if (pathname.startsWith('/us-market')) return 'us'
  if (pathname.startsWith('/crypto-market')) return 'crypto'
  if (pathname.startsWith('/hk-market')) return 'hk'
  return null
}

export function detailMarketOf(pathname: string | null): Market | null {
  if (!pathname) return null
  if (pathname.startsWith('/cn-preview')) return 'cn'
  if (pathname.startsWith('/us-preview')) return 'us'
  if (pathname.startsWith('/crypto-preview')) return 'crypto'
  if (pathname.startsWith('/hk-preview')) return 'hk'
  return null
}

/** 市场 Tab 高亮:市场首页/详情页按路由 · workbench 按 store · 其余(中性页)全不亮。 */
export function resolveActiveMarket(
  pathname: string | null,
  storeMarket: Market,
): Market | null {
  const byRoute = homeMarketOf(pathname) ?? detailMarketOf(pathname)
  if (byRoute) return byRoute
  return pathname?.startsWith('/workbench') ? storeMarket : null
}
