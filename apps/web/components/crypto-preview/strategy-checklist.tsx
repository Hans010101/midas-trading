'use client'

/**
 * 实战策略清单 · 接真实信号(M2-C.2.3 · ADR-0020 Block3 · E8 前端算)。
 *
 * 4 条规则由实时指标驱动,命中点亮 + 文案;数据未预热显示「待预热」。
 *   ① 资金费为正 + OI 增 → 顺势开多      (metrics: funding_rate>0 且 oi_change_pct_24h>0)
 *   ② 大户多空比极端 → 反向预警          (metrics: account_long_short_ratio >2 或 <0.5)
 *   ③ 缠论一卖 + 基差走弱 → 减仓          (chan 窗口内出现 S1 且 基差率<0 · 基差=mark-index 单点)
 *   ④ 强平距现价 < 5% → 降杠杆            (本币活仓 liquidation_distance_pct<5)
 *
 * 基差「走弱」单点定义:基差率 = (mark−index)/index < 0(合约贴水)· 不依赖 2.4 的时序。
 *
 * 🔴 红线:只读提示 · 绝不自动下单 · 全程虚拟。
 */

import { useQuery } from '@tanstack/react-query'

import { ProLock } from '@/components/account/pro-lock'
import { useChan } from '@/hooks/use-chan'
import { useFuturesInfo } from '@/hooks/use-crypto'
import { usePerpPositions } from '@/hooks/use-perp'
import { useQuota } from '@/hooks/use-quota'
import { fetchFuturesMetricsBatch } from '@/lib/api/crypto-market'
import { cn } from '@/lib/utils'
import type { Period } from '@midas/shared'

type RuleStatus = 'hit' | 'idle' | 'unknown'

interface Rule {
  key: string
  tone: 'green' | 'amber' | 'red'
  label: string
  status: RuleStatus
  hitText: string
  detail: string
}

interface Props {
  /** Binance 风格 'BTCUSDT' */
  futuresSymbol: string
  /** ccxt 风格 'BTC/USDT'(缠论用) */
  klineSymbol: string
  period: Period
}

export function StrategyChecklist({ futuresSymbol, klineSymbol, period }: Props) {
  // ★ Pro 门控:实战策略清单是 Pro 内容(其输入为公开合约指标 · 此处为前端门控 · 两道门遮罩)
  const { data: quota } = useQuota()
  const isPro = quota?.plan === 'pro'
  const info = useFuturesInfo(futuresSymbol)
  const metricsQ = useQuery({
    queryKey: ['crypto-strategy-metrics', futuresSymbol],
    queryFn: ({ signal }) => fetchFuturesMetricsBatch([futuresSymbol], signal),
    retry: 0,
    staleTime: 60_000,
  })
  const chanQ = useChan({
    symbol: klineSymbol, market: 'crypto', period, instrument: 'perp',
  })
  const posQ = usePerpPositions()

  const metric = metricsQ.data?.items?.find((m) => m.symbol === futuresSymbol) ?? null
  const fundingRate = metric?.funding_rate ?? info.data?.last_funding_rate ?? null
  const oiChg = metric?.oi_change_pct_24h ?? null
  const accLsr = metric?.account_long_short_ratio ?? null
  const basisPct =
    info.data != null && info.data.index_price > 0
      ? ((info.data.mark_price - info.data.index_price) / info.data.index_price) * 100
      : null
  const chanReady = chanQ.isSuccess
  const hasS1 = (chanQ.data?.buy_sell_points ?? []).some((p) => p.kind === 'S1')
  const activePos =
    (posQ.data ?? []).find((p) => p.symbol === futuresSymbol && p.closed_at === null) ?? null
  const liqDist =
    activePos?.liquidation_distance_pct != null ? Number(activePos.liquidation_distance_pct) : null

  const rules: Rule[] = [
    {
      key: 'r1',
      tone: 'green',
      label: '资金费为正 + OI 增 → 顺势开多',
      status: fundingRate == null || oiChg == null ? 'unknown' : fundingRate > 0 && oiChg > 0 ? 'hit' : 'idle',
      hitText: '🟢 多头情绪占优 · 可考虑顺势开多',
      detail:
        fundingRate != null && oiChg != null
          ? `资金费 ${(fundingRate * 100).toFixed(4)}% · OI 24H ${oiChg >= 0 ? '+' : ''}${oiChg.toFixed(2)}%`
          : '数据待预热',
    },
    {
      key: 'r2',
      tone: 'amber',
      label: '大户多空比极端 → 反向预警',
      status: accLsr == null ? 'unknown' : accLsr > 2 || accLsr < 0.5 ? 'hit' : 'idle',
      hitText: '🟡 情绪过热 · 警惕反向',
      detail: accLsr != null ? `账户多空比 ${accLsr.toFixed(2)}` : '数据待预热',
    },
    {
      key: 'r3',
      tone: 'amber',
      label: '缠论一卖 + 基差走弱 → 减仓',
      status: !chanReady || basisPct == null ? 'unknown' : hasS1 && basisPct < 0 ? 'hit' : 'idle',
      hitText: '🟡 缠论一卖 + 基差转弱 · 可考虑减仓',
      detail:
        chanReady && basisPct != null
          ? `缠论一卖 ${hasS1 ? '出现' : '无'} · 基差率 ${basisPct.toFixed(3)}%`
          : '数据待预热',
    },
    {
      key: 'r4',
      tone: 'red',
      label: '强平距现价 < 5% → 降杠杆',
      status: liqDist == null ? 'unknown' : liqDist < 5 ? 'hit' : 'idle',
      hitText: '🔴 强平距离过近 · 建议降杠杆 / 加保证金',
      detail:
        liqDist != null
          ? `强平距离 ${liqDist.toFixed(1)}%`
          : activePos == null
            ? '无本币活仓'
            : '—',
    },
  ]

  return (
    <div className="rounded-lg border border-paper bg-surface-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-serif text-base font-bold">实战策略清单</span>
      </div>
      {isPro ? (
        <>
          <ul className="space-y-2">
            {rules.map((r) => (
              <RuleRow key={r.key} rule={r} />
            ))}
          </ul>
          <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground/70">
            策略由实时指标驱动 · 命中仅作提示
          </p>
        </>
      ) : (
        <ProLock title="实战策略清单" />
      )}
    </div>
  )
}

const TONE_HIT: Record<Rule['tone'], string> = {
  green: 'bg-up/15 text-up border-up/40',
  amber: 'bg-gold/15 text-gold border-gold/40',
  red: 'bg-down/15 text-down border-down/40',
}

function RuleRow({ rule }: { rule: Rule }) {
  const hit = rule.status === 'hit'
  const unknown = rule.status === 'unknown'
  const badge =
    rule.status === 'hit' ? '命中' : rule.status === 'idle' ? '未触发' : '待预热'
  return (
    <li
      className={cn(
        'rounded-md border px-2.5 py-2 text-xs transition-colors',
        hit ? TONE_HIT[rule.tone] : 'border-paper bg-background/50 text-foreground/70',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className={cn('leading-snug', !hit && 'text-foreground/80')}>{rule.label}</span>
        <span
          className={cn(
            'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium',
            hit
              ? 'bg-background/70'
              : unknown
                ? 'border border-dashed border-paper text-muted-foreground/60'
                : 'bg-paper text-muted-foreground/70',
          )}
        >
          {badge}
        </span>
      </div>
      <div className="mt-1 text-[10px] text-muted-foreground/70">{rule.detail}</div>
      {hit && <div className="mt-1 text-[11px] font-medium">{rule.hitText}</div>}
    </li>
  )
}
