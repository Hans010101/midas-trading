'use client'

/**
 * M2-D · 加密币种详情页(接真实数据版)。
 *
 * 布局沿用 M2-D 骨架(产品方已验收通过):
 *   顶部 Header · 左主区(主图 + 6 维度图)· 右侧栏(AI 决策卡 + 下单指导 + 策略清单)
 *
 * 真实 / 占位 一眼分清:
 *   ✅ 真实数据:主图 K线+缠论 · OI · 大户多空比(账户/持仓) · taker 主动买卖 · AI 技术面 · 合约面实时指标
 *   ⏳ 占位:多空人数比值 / 基差(M2-B 数据缺口) · 下单指导 / 实战策略清单(M2-C 虚拟交易模块)
 *
 * 标的:本预览页固定 BTC(klineSymbol=BTC/USDT · futuresSymbol=BTCUSDT)。
 * 多标的切换 = 后续迭代(本步专注接数据)。
 */

import { useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'

import { TopNav } from '@/components/layout/top-nav'
import { CryptoAiCard } from '@/components/crypto-preview/crypto-ai-card'
import { CryptoHeader } from '@/components/crypto-preview/crypto-header'
import { CryptoMainChart } from '@/components/crypto-preview/crypto-main-chart'
import { CryptoPerpOrders } from '@/components/crypto-preview/crypto-perp-orders'
import { DimensionSection } from '@/components/crypto-preview/dimension-section'
import { PerpOrderGuidance } from '@/components/crypto-preview/perp-order-guidance'
import { StrategyChecklist } from '@/components/crypto-preview/strategy-checklist'
import type { Period } from '@midas/shared'

// 常见 quote · 用于把 Binance 风格 'BEATUSDT' 切回 ccxt 风格 'BEAT/USDT'
const QUOTES = ['USDT', 'USDC', 'BUSD', 'FDUSD'] as const
const DEFAULT_KLINE = 'BTC/USDT'
const DEFAULT_FUTURES = 'BTCUSDT'

/**
 * 由 URL ?symbol= 推导两种风格的 symbol:
 *   - futuresSymbol:Binance 风格无斜杠(crypto futures 端点 / 列表页传入)
 *   - klineSymbol:ccxt 风格带斜杠(/market/kline · /analysis/* 用)
 * 无参数 / 非法 / 无法识别 quote → 默认 BTC(绝不崩、绝不留空)。
 */
function deriveSymbols(raw: string | null): { klineSymbol: string; futuresSymbol: string } {
  const s = (raw ?? '').trim().toUpperCase()
  if (!s) return { klineSymbol: DEFAULT_KLINE, futuresSymbol: DEFAULT_FUTURES }
  if (s.includes('/')) {
    // 已是 ccxt 风格(容错:列表页其实传无斜杠,这里兼容两种)
    return { klineSymbol: s, futuresSymbol: s.replace('/', '') }
  }
  const quote = QUOTES.find((q) => s.endsWith(q) && s.length > q.length)
  if (!quote) return { klineSymbol: DEFAULT_KLINE, futuresSymbol: DEFAULT_FUTURES }
  return { klineSymbol: `${s.slice(0, -quote.length)}/${quote}`, futuresSymbol: s }
}

export function CryptoDetail() {
  const searchParams = useSearchParams()
  const { klineSymbol, futuresSymbol } = useMemo(
    () => deriveSymbols(searchParams.get('symbol')),
    [searchParams],
  )
  // 默认周期 1h(全市场详情页统一 · 15m/1h/1d 可切 · K线/缠论/AI卡跟随)
  const [period, setPeriod] = useState<Period>('1h')

  return (
    <main className="min-h-screen bg-background text-foreground">
      <TopNav />

      <CryptoHeader
        klineSymbol={klineSymbol}
        futuresSymbol={futuresSymbol}
        period={period}
        onPeriodChange={setPeriod}
      />

      <div className="mx-auto flex max-w-[1600px] gap-4 px-4 py-4">
        {/* 左主区 */}
        <div className="flex-1 space-y-4">
          <CryptoMainChart symbol={klineSymbol} period={period} />
          <DimensionSection futuresSymbol={futuresSymbol} />
        </div>

        {/* 右侧栏 */}
        <aside className="w-[360px] shrink-0 space-y-4">
          <CryptoAiCard
            klineSymbol={klineSymbol}
            futuresSymbol={futuresSymbol}
            period={period}
          />
          <PerpOrderGuidance futuresSymbol={futuresSymbol} klineSymbol={klineSymbol} />
          <CryptoPerpOrders futuresSymbol={futuresSymbol} />
          <StrategyChecklist
            futuresSymbol={futuresSymbol}
            klineSymbol={klineSymbol}
            period={period}
          />
        </aside>
      </div>
    </main>
  )
}

// ============================================================
// 右栏 2 · 下单指导 → 已接真实(PerpOrderGuidance · M2-C.1 · ADR-0019)
// ============================================================
// (占位组件已删 · 替换为 components/crypto-preview/perp-order-guidance.tsx)

// 右栏 3 · 实战策略清单 → 已接真实(StrategyChecklist · M2-C.2.3 · ADR-0020 Block3)
// (占位组件已删 · 替换为 components/crypto-preview/strategy-checklist.tsx)
