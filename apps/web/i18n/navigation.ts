import { createNavigation } from 'next-intl/navigation'

import { routing } from './routing'

/**
 * next-intl locale 感知导航(Phase 0 激活 · 决策 2 as-needed)。
 *
 * ★为什么全站导航要走这里而非裸 next/link · next/navigation:
 *   as-needed 下英文 URL 带 `/en` 前缀、中文无前缀。这套 wrapper 会自动按当前 locale
 *   给 href/push 补前缀(中文不补 · 英文补 /en),usePathname 反过来【剥掉】locale 前缀
 *   还原成无前缀路径 —— 全站导航高亮 / 路由保护判定拿到的又是 `/account` 而非 `/en/account`,
 *   既存的纯函数 helper(market-nav / account-nav)+ 其 vitest 零改。
 *
 * ★usePathname 是隐形炸弹:裸 next/navigation 的 usePathname 返回含 locale 的 `/en/xxx`,
 *   本 wrapper 剥掉前缀。凡靠 pathname 做 startsWith 精确匹配的消费方都必须用这里的版本。
 */
export const { Link, useRouter, usePathname, redirect, getPathname } = createNavigation(routing)
