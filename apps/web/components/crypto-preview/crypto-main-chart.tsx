'use client'

/**
 * M2-D · 主图 · 真实 K 线 + 布林带 + MACD 副图 + 缠论标注。
 *
 * 复用工作台同款组件:
 *   · KlineChart   → /api/v1/market/kline · 用 indicators 开 BOLL(主图叠加)+ MACD(副图)
 *                    指标计算走 klinecharts 内置 BOLL / MACD(标准参数 20,2 / 12,26,9)
 *   · ChanOverlay  → /api/v1/analysis/chan(props 驱动 · 不污染 workbench store)
 *
 * 三个图层独立开关(默认全开):布林带 / MACD / 缠论标注。
 * 布林带在主图叠加,跟缠论标注(笔/中枢/分型)同层共存,不冲突
 * (BOLL 走 indicator,缠论走 overlay,klinecharts 两套机制互不覆盖)。
 *
 * MACD 柱:红涨绿跌(A 股传统 · CLAUDE.md 视觉系统)· 覆盖 klinecharts 默认的绿涨红跌。
 * DIF 帝王金 / DEA 中国红 · 跟点金主色一致。
 * 周期由父组件传入(15m / 1h / 1d · kline period enum 无 4h · 见交付说明)。
 */

import type { Chart } from 'klinecharts'
import { useMemo, useState } from 'react'

import { ChanOverlay } from '@/components/chart/chan-overlay'
import { KlineChart } from '@/components/chart/kline-chart'
import { StrategyOverlay } from '@/components/chart/strategy-overlay'
import { StrategyPanel } from '@/components/chart/strategy-panel'
import type { StrategyKind } from '@/lib/api/strategy'
import { readDisplayPrefs } from '@/lib/display-prefs'
import { cn } from '@/lib/utils'
import type { IndicatorName } from '@/lib/store/workbench-store'
import type { Period } from '@midas/shared'

// MACD 样式覆盖 · 红涨绿跌 + DIF 帝王金 / DEA 中国红(CLAUDE.md 视觉系统)
// MACD 只有一个柱图 figure,bars[0] 控制柱的涨跌色,跟 figure 顺序无关 · 稳。
const MACD_STYLES = {
  bars: [{ upColor: '#DC143C', downColor: '#0F6E5F', noChangeColor: '#94949C' }],
  lines: [{ color: '#B8860B' }, { color: '#C8102E' }], // DIF 帝王金 / DEA 中国红
}

// 布林带叠在主图 K 线上 · 跟缠论标注(笔=金 / 中枢=淡灰蓝 / 分型=红绿三角)同框,
// 刻意避开缠论用色:不用帝王金(=笔)· 不用 #6482A0 蓝灰(=中枢保留色)· 不用红绿(=分型/涨跌)。
// 三条线统一中性灰 + 细线宽 1 · 呈「包裹 K 线的通道」观感 · 清晰但不抢眼,不跟缠论抢视觉。
const BOLL_STYLES = {
  lines: [
    { color: '#8C8C8C', size: 1 },
    { color: '#8C8C8C', size: 1 },
    { color: '#8C8C8C', size: 1 },
  ],
}

interface CryptoMainChartProps {
  /** ccxt 风格 symbol · 'BTC/USDT' */
  symbol: string
  period: Period
}

export function CryptoMainChart({ symbol, period }: CryptoMainChartProps) {
  const [chart, setChart] = useState<Chart | null>(null)
  // ★刀2:指标开关初值读 display_prefs(同步 lazy init · 客户端渲染无 SSR mismatch · 无闪烁)·
  //   临时拨开关只 setState、★不回写 cookie(偏好默认值只在设置页改)。
  const [chanEnabled, setChanEnabled] = useState(() => readDisplayPrefs().indicators.chan)
  const [bollEnabled, setBollEnabled] = useState(() => readDisplayPrefs().indicators.boll)
  const [macdEnabled, setMacdEnabled] = useState(() => readDisplayPrefs().indicators.macd)
  // 形态A 策略信号 = 做T(dott)层 · 初值读 dott 偏好 · ★Pro 门控独立(后端 locked 空壳 +
  // 前端遮罩处理)· 偏好只设「默认开关初值」,非 Pro 即使 dott=true 门控仍挡,偏好不绕过权限。
  const [strategy, setStrategy] = useState<StrategyKind>('ma_cross')
  const [strategyEnabled, setStrategyEnabled] = useState(() => readDisplayPrefs().indicators.dott)

  // useMemo 稳定引用 · 否则每次 render 新对象会让 KlineChart 反复重建指标
  const indicators = useMemo<Record<IndicatorName, boolean>>(
    () => ({ MA: false, BOLL: bollEnabled, MACD: macdEnabled, RSI: false }),
    [bollEnabled, macdEnabled],
  )
  const indicatorStyles = useMemo(
    () => ({
      MACD: MACD_STYLES as Record<string, unknown>,
      BOLL: BOLL_STYLES as Record<string, unknown>,
    }),
    [],
  )

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-paper bg-surface-card p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="font-serif text-sm font-bold">主图:K 线 + 布林带 + MACD + 缠论</span>
          {/* 移动刀C(B3):指标参数窄屏隐藏(挤压换行噪声)· lg+ 原样 */}
          <span className="ml-2 hidden text-[11px] text-muted-foreground/50 lg:inline">
            BOLL(20,2)· MACD(12,26,9)· 笔(金)/ 分型 / 中枢
          </span>
        </div>
        <div className="flex items-center gap-2">
          <ToggleChip label="布林带" on={bollEnabled} onClick={() => setBollEnabled((v) => !v)} />
          <ToggleChip label="MACD" on={macdEnabled} onClick={() => setMacdEnabled((v) => !v)} />
          <ToggleChip label="缠论标注" on={chanEnabled} onClick={() => setChanEnabled((v) => !v)} />
        </div>
      </div>

      <div className="h-[460px] overflow-hidden rounded-md border border-paper">
        <KlineChart
          symbol={symbol}
          market="crypto"
          instrument="perp"
          period={period}
          indicators={indicators}
          indicatorStyles={indicatorStyles}
          onChartReady={setChart}
        />
      </div>

      {/* 缠论标注层 · props 驱动(不读 workbench store)· 跟布林带同层共存 · 合约 K 线缠论 */}
      <ChanOverlay
        chart={chart}
        symbol={symbol}
        market="crypto"
        instrument="perp"
        period={period}
        enabled={chanEnabled}
      />
      {/* 策略信号标注层 · 独立 groupId(midas-strategy-overlay)· 不干扰缠论 */}
      <StrategyOverlay
        chart={chart}
        symbol={symbol}
        market="crypto"
        instrument="perp"
        period={period}
        strategy={strategy}
        enabled={strategyEnabled}
      />
      </div>

      {/* AI 策略面板:选择器 + 推荐 + 触发状态(展示型 · 不下单)*/}
      <StrategyPanel
        symbol={symbol}
        market="crypto"
        instrument="perp"
        period={period}
        strategy={strategy}
        onStrategyChange={setStrategy}
        enabled={strategyEnabled}
        onToggle={() => setStrategyEnabled((v) => !v)}
      />
    </div>
  )
}

function ToggleChip({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md border px-3 py-1 text-xs transition-colors',
        on
          ? 'border-gold bg-gold/10 text-gold'
          : 'border-paper text-muted-foreground hover:border-gold/60',
      )}
    >
      {label} {on ? '开' : '关'}
    </button>
  )
}
