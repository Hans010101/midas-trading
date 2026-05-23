/**
 * M2-D · 加密币种详情页 · 接真实数据版。
 *
 * 骨架版(force-static · 全占位)产品方已验收布局通过 → 本版升级为接真实数据:
 *   ✅ 真实:主图 K线+缠论 · OI · 大户多空比(账户/持仓) · taker 主动买卖 ·
 *           AI 技术面决策(0012)· 合约面实时指标(资金费率/OI/多空比)
 *   ⏳ 占位:多空人数比值 / 基差(M2-B 数据缺口)· 下单指导 / 策略清单(M2-C 虚拟交易)
 *
 * 数据走已上线后端 REST(/api/v1/market · /api/v1/analysis · /api/v1/crypto)·
 * 客户端 TanStack Query 取数 · 接不上的一律占位 / 显示「—」· 绝不伪造(CLAUDE.md 红线)。
 *
 * 路由:Next.js App Router app/crypto-preview/page.tsx → /crypto-preview ·
 *       middleware 不保护此路径 · 匿名可访问。
 *
 * 红线:点金永远只用虚拟资金 · 绝不接真实交易通道。
 */

import { Suspense } from 'react'

import { CryptoDetail } from '@/components/crypto-preview/crypto-detail'

export default function CryptoPreviewPage() {
  // CryptoDetail 用 useSearchParams 读 ?symbol= · App Router 要求包 Suspense 边界
  return (
    <Suspense fallback={<main className="min-h-screen bg-background" />}>
      <CryptoDetail />
    </Suspense>
  )
}
