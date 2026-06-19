'use client'

/**
 * M2-D · AI 决策卡(合并版 · 技术面 + 合约面 多空研判)。
 *
 * 两段真实数据,语义分清:
 *
 *  A. 技术面 / 缠论(综合评分)
 *     → /api/v1/analysis/decision-card(0012 ADR · 单 Agent 技术面)
 *     · composite_score / label / 置信度 / narrative / 缠论买卖点
 *     · 后端未配 DEEPSEEK_API_KEY 时 llm_mode='mock' · footer 标 mock(不假装真实)
 *
 *  B. 多空研判(合约面)· 实时指标 + 透明规则解读
 *     → 资金费率(futures/info)· OI 增减(open-interest)· 大户多空比(long-short-ratio)
 *     · 只列【真实指标值】+【简单规则标签】· 不编造一个合约面综合评分
 *     · 合约面评分算法 = M2-B/M2-C 待定义(如实标注)· 绝不硬编假公式
 *
 * 红线:全程虚拟。
 */

import { Loader2 } from 'lucide-react'

import { TradingPlanBlock } from '@/components/ai/trading-plan-block'
import { ProLock } from '@/components/account/pro-lock'
import { useAiDecision } from '@/hooks/use-ai-decision'
import {
  useFuturesInfo,
  useLongShortRatio,
  useOpenInterest,
} from '@/hooks/use-crypto'
import type { CompositeLabel, DecisionCard } from '@/lib/api/ai-decision'
import { cn } from '@/lib/utils'
import type { Period } from '@midas/shared'

interface CryptoAiCardProps {
  klineSymbol: string // 'BTC/USDT'
  futuresSymbol: string // 'BTCUSDT'
  period: Period
}

export function CryptoAiCard({ klineSymbol, futuresSymbol, period }: CryptoAiCardProps) {
  // 合约(perp)技术面 · 跟主图/缠论/Header 同源,保证全链路一致
  const decision = useAiDecision({ symbol: klineSymbol, market: 'crypto', period, instrument: 'perp' })
  // 操作建议(0036 批次甲)· crypto → open_long/open_short(合约)· hold/中性不出文案
  const adv = decision.status === 'success' ? decision.data.actionable : null
  const plan = decision.status === 'success' ? decision.data.trading_plan : null

  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <div className="mb-3">
        <span className="font-serif text-base font-bold text-midas-red">AI 决策卡</span>
      </div>

      {/* A · 技术面综合评分 */}
      {decision.status === 'pending' && <Skeleton />}
      {decision.status === 'error' && (
        <ErrorNote onRetry={() => void decision.refetch()} />
      )}
      {decision.status === 'success' &&
        (decision.data.locked
          ? <ProLock title="AI 决策分析" className="mb-3" />
          : <CompositeBlock card={decision.data} />)}

      {/* A2 · AI 操作建议 + 一键模拟下单(0036 批次甲 · 走 ai-order → 同一虚拟撮合引擎 execute)*/}
      {adv && (
        <div className="mb-3 border-t border-paper pt-2">
          <p className="mb-1 text-[10px] text-muted-foreground/70">操作建议</p>
          <p className="text-xs leading-relaxed text-foreground">{adv.hint}</p>
          <p className="mt-0.5 text-[10px] text-muted-foreground/60">
            {adv.basis} · 仓位:{adv.size_note}
          </p>
        </div>
      )}

      {/* B · 多空研判(合约面)· 实时指标 + 规则解读 */}
      <ContractRead futuresSymbol={futuresSymbol} />

      {/* C · 交易计划参考(三价位 + plan_note + 按计划价挂限价单)· 合约面之后 */}
      {decision.status === 'success' && !decision.data.locked && (
        <TradingPlanBlock plan={plan} symbol={klineSymbol} market="crypto" actionable={adv} />
      )}
    </div>
  )
}

// ── A · 技术面综合评分 ─────────────────────────────────────────────────────
function CompositeBlock({ card }: { card: DecisionCard }) {
  const color = labelColor(card.composite_label)
  return (
    <div className="mb-3">
      <div className="mb-2 flex items-end gap-2">
        <span className={cn('font-mono text-3xl font-bold', color)}>
          {card.composite_score > 0 ? '+' : ''}
          {card.composite_score}
        </span>
        <span className={cn('mb-1 text-sm', color)}>
          {card.composite_label} · 置信度 {(card.composite_confidence * 100).toFixed(0)}%
        </span>
      </div>

      <div className="text-xs text-foreground/80">
        <p className="leading-relaxed">{card.narrative}</p>
      </div>

      {card.chan_signals.length > 0 && (
        <ul className="mt-2 space-y-1">
          {card.chan_signals.slice(-3).reverse().map((s, i) => {
            const isBuy = s.kind.startsWith('B')
            return (
              <li key={`${s.kind}-${s.ts}-${i}`} className="flex items-center gap-2 text-[11px]">
                <span
                  className={cn(
                    'inline-flex h-5 w-7 shrink-0 items-center justify-center rounded font-mono text-[10px] font-bold',
                    isBuy ? 'bg-up/10 text-up' : 'bg-down/10 text-down',
                  )}
                >
                  {s.kind}
                </span>
                <span className="font-mono tabular-nums text-foreground">{s.price.toFixed(2)}</span>
                <span className="truncate text-muted-foreground/70">{s.description}</span>
              </li>
            )
          })}
        </ul>
      )}

      <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground/60">
        <span>{card.cached ? '· 缓存命中' : '· 实时计算'}</span>
        {card.llm_mode === 'mock' && (
          <span className="rounded bg-gold/10 px-1.5 py-0.5 font-mono text-gold">
            mock(待填 KEY)
          </span>
        )}
      </div>
    </div>
  )
}

// ── B · 多空研判(合约面)· 真实指标 + 透明规则 ────────────────────────────
function ContractRead({ futuresSymbol }: { futuresSymbol: string }) {
  const info = useFuturesInfo(futuresSymbol)
  const lsr = useLongShortRatio(futuresSymbol, 96)
  const oi = useOpenInterest(futuresSymbol, 96)

  const fundingRate = info.data?.last_funding_rate ?? null

  const lsrItems = lsr.data?.items ?? []
  const lastLsr = lsrItems.at(-1)
  const posRatio = lastLsr?.top_position_ratio ?? null
  const accRatio = lastLsr?.top_account_ratio ?? null

  const oiItems = oi.data?.items ?? []
  const oiFirst = oiItems.at(0)?.oi_usd ?? null
  const oiLast = oiItems.at(-1)?.oi_usd ?? null
  const oiChangePct =
    oiFirst !== null && oiLast !== null && oiFirst !== 0
      ? ((oiLast - oiFirst) / oiFirst) * 100
      : null

  const anyData = fundingRate !== null || posRatio !== null || oiChangePct !== null
  const anyLoading = info.isPending || lsr.isPending || oi.isPending

  return (
    <div className="mb-3 rounded-md bg-background/60 p-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">多空研判(合约面)</span>
        <span className="text-[10px] text-muted-foreground/50">实时指标 · 规则解读</span>
      </div>

      {anyLoading && !anyData ? (
        <p className="py-2 text-center text-[11px] text-muted-foreground/60">加载合约指标…</p>
      ) : !anyData ? (
        <p className="py-2 text-center text-[11px] text-muted-foreground/60">
          暂无合约指标 · 预览环境未预热 / 待采集
        </p>
      ) : (
        <ul className="space-y-1 text-xs text-foreground/80">
          <FactorLine
            label="资金费率"
            value={fundingRate !== null ? `${fundingRate >= 0 ? '+' : ''}${(fundingRate * 100).toFixed(4)}%` : '—'}
            tag={
              fundingRate === null
                ? null
                : fundingRate >= 0
                  ? { text: '多头付费 · 偏多情绪', tone: 'bull' }
                  : { text: '空头付费 · 偏空情绪', tone: 'bear' }
            }
          />
          <FactorLine
            label="大户持仓多空比"
            value={posRatio !== null ? posRatio.toFixed(2) : '—'}
            tag={
              posRatio === null
                ? null
                : posRatio >= 1
                  ? { text: '持仓偏多', tone: 'bull' }
                  : { text: '持仓偏空', tone: 'bear' }
            }
          />
          <FactorLine
            label="大户账户多空比"
            value={accRatio !== null ? accRatio.toFixed(2) : '—'}
            tag={
              accRatio === null
                ? null
                : accRatio >= 1
                  ? { text: '账户偏多', tone: 'bull' }
                  : { text: '账户偏空', tone: 'bear' }
            }
          />
          <FactorLine
            label="OI 区间变化(8h)"
            value={oiChangePct !== null ? `${oiChangePct >= 0 ? '+' : ''}${oiChangePct.toFixed(2)}%` : '—'}
            tag={
              oiChangePct === null
                ? null
                : oiChangePct >= 0
                  ? { text: '增仓', tone: 'bull' }
                  : { text: '减仓', tone: 'bear' }
            }
          />
        </ul>
      )}

    </div>
  )
}

function FactorLine({
  label,
  value,
  tag,
}: {
  label: string
  value: string
  tag: { text: string; tone: 'bull' | 'bear' } | null
}) {
  return (
    <li className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground/80">{label}</span>
      <span className="flex items-center gap-2">
        <span className="font-mono tabular-nums text-foreground">{value}</span>
        {tag && (
          <span className={cn('text-[10px]', tag.tone === 'bull' ? 'text-up' : 'text-down')}>
            {tag.text}
          </span>
        )}
      </span>
    </li>
  )
}

// ── states ─────────────────────────────────────────────────────────────────
function Skeleton() {
  return (
    <div className="mb-3 flex flex-col items-center justify-center gap-2 py-6">
      <Loader2 className="h-6 w-6 animate-spin text-midas-red" />
      <p className="text-xs text-muted-foreground/70">AI 思考中…</p>
    </div>
  )
}

function ErrorNote({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="mb-3 rounded-md border border-dashed border-paper bg-background/60 p-3 text-center">
      <p className="mb-2 text-xs text-muted-foreground/80">暂时无法生成技术面决策</p>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center rounded-md border border-midas-red px-3 py-1 text-xs text-midas-red transition-colors hover:bg-midas-red-glow"
      >
        重试
      </button>
    </div>
  )
}

function labelColor(label: CompositeLabel): string {
  switch (label) {
    case '强多':
    case '弱多':
      return 'text-up'
    case '强空':
    case '弱空':
      return 'text-down'
    default:
      return 'text-muted-foreground'
  }
}
