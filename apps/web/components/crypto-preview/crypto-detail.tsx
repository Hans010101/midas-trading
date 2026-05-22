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

import { useState } from 'react'

import { CryptoAiCard } from '@/components/crypto-preview/crypto-ai-card'
import { CryptoHeader } from '@/components/crypto-preview/crypto-header'
import { CryptoMainChart } from '@/components/crypto-preview/crypto-main-chart'
import { DimensionSection } from '@/components/crypto-preview/dimension-section'
import { VirtualBadge } from '@/components/ui/virtual-badge'
import type { Period } from '@midas/shared'

const KLINE_SYMBOL = 'BTC/USDT'
const FUTURES_SYMBOL = 'BTCUSDT'

export function CryptoDetail() {
  const [period, setPeriod] = useState<Period>('1d')

  return (
    <main className="min-h-screen bg-background text-foreground">
      {/* 顶部说明条:本页真实 / 占位的边界 */}
      <div className="border-b border-dashed border-gold/60 bg-gold/10 px-6 py-2 text-center text-xs text-gold">
        M2-D 详情页 · 主图 / OI / 大户多空比 / 主动买卖 = 真实数据 ·
        多空人数比 / 基差 = M2-B 待补 · 下单指导 / 策略清单 = M2-C 待接
      </div>

      <CryptoHeader
        klineSymbol={KLINE_SYMBOL}
        futuresSymbol={FUTURES_SYMBOL}
        period={period}
        onPeriodChange={setPeriod}
      />

      <div className="mx-auto flex max-w-[1600px] gap-4 px-4 py-4">
        {/* 左主区 */}
        <div className="flex-1 space-y-4">
          <CryptoMainChart symbol={KLINE_SYMBOL} period={period} />
          <DimensionSection futuresSymbol={FUTURES_SYMBOL} />
        </div>

        {/* 右侧栏 */}
        <aside className="w-[360px] shrink-0 space-y-4">
          <CryptoAiCard
            klineSymbol={KLINE_SYMBOL}
            futuresSymbol={FUTURES_SYMBOL}
            period={period}
          />
          <OrderGuidance />
          <StrategyChecklist />
        </aside>
      </div>
    </main>
  )
}

// ============================================================
// 右栏 2 · 下单指导(占位 · 待虚拟交易模块接入 M2-C)· 全程虚拟资金
// ============================================================
function OrderGuidance() {
  return (
    <div className="rounded-lg border border-dashed border-gold/60 bg-gold/5 p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-serif text-base font-bold">下单指导</span>
        <VirtualBadge size="sm" />
      </div>
      <p className="mb-3 rounded bg-gold/15 px-2 py-1 text-[11px] text-gold">
        【占位 · 待虚拟交易模块接入(M2-C)】
      </p>
      <div className="space-y-2 text-sm opacity-60">
        <div className="flex gap-2">
          <span className="flex-1 rounded bg-bull/15 py-1.5 text-center text-bull">开多(虚拟)</span>
          <span className="flex-1 rounded bg-bear/15 py-1.5 text-center text-bear">开空(虚拟)</span>
        </div>
        <div className="flex items-center justify-between rounded border border-paper px-2 py-1.5 text-xs text-muted-foreground">
          <span>杠杆</span>
          <span className="font-mono">— (待接)</span>
        </div>
        <div className="flex items-center justify-between rounded border border-paper px-2 py-1.5 text-xs text-muted-foreground">
          <span>保证金(虚拟 USDT)</span>
          <span className="font-mono">— (待接)</span>
        </div>
        <div className="flex items-center justify-between rounded border border-paper px-2 py-1.5 text-xs text-muted-foreground">
          <span>预估强平价</span>
          <span className="font-mono">— (待接)</span>
        </div>
      </div>
      <p className="mt-3 text-[10px] text-muted-foreground/70">
        全程虚拟资金 · 绝不接真实交易所下单 · 所有动作走点金虚拟撮合(M2-C)
      </p>
    </div>
  )
}

// ============================================================
// 右栏 3 · 实战策略清单(占位 · 待虚拟交易模块接入 M2-C)
// ============================================================
function StrategyChecklist() {
  return (
    <div className="rounded-lg border border-dashed border-gold/60 bg-gold/5 p-4">
      <div className="mb-2 font-serif text-base font-bold">实战策略清单</div>
      <p className="mb-3 rounded bg-gold/15 px-2 py-1 text-[11px] text-gold">
        【占位 · 待虚拟交易模块接入(M2-C)】
      </p>
      <ul className="space-y-2 text-xs text-foreground/70 opacity-60">
        <li className="flex gap-2"><span className="text-gold">▢</span> 资金费率为正且 OI 增 → 顺势虚拟开多</li>
        <li className="flex gap-2"><span className="text-gold">▢</span> 大户多空比极端 → 反向预警</li>
        <li className="flex gap-2"><span className="text-gold">▢</span> 缠论一卖 + 基差走弱 → 虚拟减仓</li>
        <li className="flex gap-2"><span className="text-gold">▢</span> 强平价距现价 &lt; 5% → 降杠杆提示</li>
      </ul>
      <p className="mt-3 text-[10px] text-muted-foreground/70">
        策略仅供参考,不构成投资建议 · 全程虚拟
      </p>
    </div>
  )
}
