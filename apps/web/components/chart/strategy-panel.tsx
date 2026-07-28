'use client'

/**
 * AI 策略面板 · 形态A 单元3(ADR 0037 §5.2)。
 *
 * 一处统一组件,三套主图(工作台 / 现货详情 / 合约详情)共用:
 * - 策略信号总开关(默认关 · 不干扰现有缠论/指标)
 * - 多个策略选择(均线金叉 / RSI 反弹 / 布林均值回归 / …)· 选中高亮
 * - AI 推荐徽章(调 /strategy-recommend · 纯规则 · 显示「推荐 XX + 理由」)
 * - 当前是否触发提示(调 /strategy-signals · current_triggered / 最近信号)
 * - ★布林做T(仅 crypto · 做T B-2 重构):标签排里一个「布林做T」标签 · 点击展开看单币布林 6 态
 *   结构(读 B-1 /crypto/boll-structure)· 【布林结构层】客观描述 · 区别 AI 决策卡综合研判(化解
 *   两块手表)· ★Pro 门控(非 Pro 显 ProLock · 同策略信号/AI卡 · 纯前端门控同 strategy-checklist)·
 *   常显(crypto 面板恒展开 · 标签可见可排序 · 仅内容遮罩)· 倾向只偏多/偏空/中性。
 *
 * ★ 全 props 驱动 · 信号点的实际标注在 <StrategyOverlay>(同 strategy/enabled 状态由父组件管理)。
 * ★ 红线:纯展示 · 不下单 / 不自动交易。
 */

import { useEffect, useState } from 'react'

import { ProLock } from '@/components/account/pro-lock'
import { biasTone } from '@/components/crypto/boll-scan-list'
import { useQuota } from '@/hooks/use-quota'
import { hasFullFeatureAccess } from '@/lib/features'
import { useStrategyRecommend, useStrategySignals } from '@/hooks/use-strategy'
import type { BollStructureResponse } from '@/lib/api/crypto-market'
import { fetchBollStructure } from '@/lib/api/crypto-market'
import type { Instrument, StrategyKind, StrategySignal } from '@/lib/api/strategy'
import { useUiStore } from '@/lib/store/ui-store-provider'
import { availableStrategies, effectiveOrder } from '@/lib/strategy-order'
import { cn } from '@/lib/utils'
import type { Market, Period } from '@midas/shared'
import { useQuery, type UseQueryResult } from '@tanstack/react-query'

const STRATEGY_LABELS: Record<StrategyKind, string> = {
  ma_cross: '均线金叉',
  rsi_reversal: 'RSI 反弹',
  boll_reversion: '布林均值回归',
  macd_cross: 'MACD 金叉死叉',
  kdj_cross: 'KDJ 金叉死叉',
  extreme: '合约极端',
}

// ★布林做T 作为标签序列里的一个特殊 token(非 StrategyKind · 独立布林结构 view)· 仅 crypto 出现。
const DOTT_TAB = 'dott' as const
type TabKey = StrategyKind | typeof DOTT_TAB
const DOTT_LABEL = '布林做T'

// 价格符号(按市场)· cn ¥ / hk HK$ / us·crypto $
function priceSym(market: Market): string {
  return market === 'cn' ? '¥' : market === 'hk' ? 'HK$' : '$'
}
// 信号价格(智能小数 · ≥1000 整数千分位 · ≥1 两位 · <1 四位)+ 市场符号
function fmtSignalPrice(price: number, market: Market): string {
  const d = price >= 1000 ? 0 : price >= 1 ? 2 : 4
  return `${priceSym(market)}${price.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`
}
// 信号时间(月/日 时:分)
function fmtSignalTs(ts: string): string {
  try {
    const d = new Date(ts)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch {
    return ts.slice(5, 16)
  }
}
// ⑤ 关键价位(批2)· 智能小数去尾零 · 不带货币符号(键已表意 · 如「MA5 10.2 · MA20 10.05」)
function fmtLevelVal(v: number): string {
  const d = v >= 1000 ? 0 : v >= 1 ? 2 : 4
  return v.toLocaleString('en-US', { maximumFractionDigits: d })
}
function fmtLevels(levels: Record<string, number>): string {
  return Object.entries(levels)
    .map(([k, v]) => `${k} ${fmtLevelVal(v)}`)
    .join(' · ')
}
// 布林做T 三轨/现价(智能小数 · ≥1 两位 · <1 四位)· 无货币符(键已表意「上/中/下」)
function fmtN(n: number): string {
  if (n >= 1) return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return n.toFixed(4)
}

interface Props {
  symbol: string
  market: Market
  period: Period
  instrument?: Instrument
  strategy: StrategyKind
  onStrategyChange: (s: StrategyKind) => void
  enabled: boolean
  onToggle: () => void
}

export function StrategyPanel({
  symbol,
  market,
  period,
  instrument,
  strategy,
  onStrategyChange,
  enabled,
  onToggle,
}: Props) {
  const recommend = useStrategyRecommend({ symbol, market, period, instrument, enabled })
  const signals = useStrategySignals({ symbol, market, period, strategy, instrument, enabled })
  const storedOrder = useUiStore((s) => s.strategyOrder)
  const setOrder = useUiStore((s) => s.setStrategyOrder)
  const dottTabPos = useUiStore((s) => s.dottTabPos)
  const setDottTabPos = useUiStore((s) => s.setDottTabPos)

  // ★布林做T(做T B-2 重构)· 仅 crypto · 标签排里一个「布林做T」标签,点开看布林结构(读 B-1)。
  //   view 切「做T结构 / 策略信号」· crypto 默认进做T(常显)· 非 crypto 恒为策略(无做T 标签)。
  const isCrypto = market === 'crypto'
  const [view, setView] = useState<'dott' | 'strategy'>(isCrypto ? 'dott' : 'strategy')
  // ★布林做T Pro 门控(纯前端 · 对齐 strategy-checklist「公开输入 + 前端门控」范式):
  //   非 Pro → 结构内容显 ProLock(标签仍在序列、仍可排序)· 不取数(不把 Pro 内容拉到非 Pro 客户端)。
  const { data: quota } = useQuota()
  const hasAccess = hasFullFeatureAccess(quota !== undefined, quota?.plan)
  const bollSymbol = symbol.replace('/', '') // ccxt 'BTC/USDT' → Binance 'BTCUSDT'(B-1 接口契约)
  const bollStructure = useQuery({
    queryKey: ['boll-structure', bollSymbol],
    queryFn: ({ signal }) => fetchBollStructure(bollSymbol, signal),
    enabled: isCrypto && view === 'dott' && hasAccess,
    retry: 0,
    staleTime: 60_000,
  })

  const rec = recommend.data
  const sig = signals.data
  const order = effectiveOrder(storedOrder, availableStrategies(market, instrument))
  // ★统一标签序列:把「布林做T」(dott)作为一个 token 插进策略序列 → 和策略标签一样能左右调 + 持久化。
  //   非 crypto 无 dott → tabs 就是 order(行为字节级不变)。dottTabPos 越界夹到末尾。
  const dottPos = Math.min(Math.max(dottTabPos, 0), order.length)
  const tabs: TabKey[] = isCrypto
    ? [...order.slice(0, dottPos), DOTT_TAB, ...order.slice(dottPos)]
    : order

  // 选中策略在当前市场不可用(如从 crypto perp 选着「合约极端」切到现货)→ 回退首个可用,
  // 避免「选中态无对应按钮 + 拉取空信号」。order 内容变化才触发(join 当稳定依赖)。
  const orderKey = order.join('|')
  useEffect(() => {
    if (order.length > 0 && !order.includes(strategy)) {
      onStrategyChange(order[0])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderKey, strategy, onStrategyChange])

  // 左右移(统一序列 · 含布林做T)· 与相邻项交换。dott 移动 → 写 dottTabPos;策略相对序变 → 写 strategyOrder。
  //   两者都持久化(ui-store)· 端点越界则不动。i = 在 tabs(统一序列)里的下标。
  function moveTab(i: number, dir: -1 | 1): void {
    const j = i + dir
    if (j < 0 || j >= tabs.length) return
    const next = [...tabs]
    ;[next[i], next[j]] = [next[j], next[i]]
    const newDottPos = next.indexOf(DOTT_TAB)
    const newOrder = next.filter((k): k is StrategyKind => k !== DOTT_TAB)
    setOrder(newOrder)
    if (isCrypto && newDottPos !== dottPos) setDottTabPos(newDottPos)
  }

  return (
    <div className="rounded-lg border border-paper bg-surface-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="font-serif text-sm font-bold">AI 策略信号</span>
          <span className="ml-2 text-[11px] text-muted-foreground/50">
            买卖信号标在 K 线 · 朱红买点 / 墨绿卖点
          </span>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className={cn(
            'rounded-md border px-3 py-1 text-xs transition-colors',
            enabled
              ? 'border-gold bg-gold/10 text-gold'
              : 'border-paper text-muted-foreground hover:border-gold/60',
          )}
        >
          策略信号 {enabled ? '开' : '关'}
        </button>
      </div>

      {/* ★crypto 恒展开(常显做T)· 非 crypto 维持原行为(仅 enabled 时展开)*/}
      {(enabled || isCrypto) && (
        <div className="mt-3 space-y-2">
          {/* 标签排:统一序列(布林做T[仅 crypto] + 策略)· 每项都有 ◀▶ 左右调 → 滑动体验一致 ·
              布林做T 也纳入 reorder(★修复:不再是序列外固定项)· 点 dott→结构视图 / 点策略→信号视图 */}
          <div className="flex flex-wrap items-center gap-2">
            {tabs.map((k, idx) => {
              const label = k === DOTT_TAB ? DOTT_LABEL : STRATEGY_LABELS[k]
              const active = k === DOTT_TAB ? view === 'dott' : view === 'strategy' && strategy === k
              const isRecommended = k !== DOTT_TAB && rec?.recommended_strategy === k
              return (
                <div key={k} className="flex items-center gap-0.5">
                  <button
                    type="button"
                    aria-label={`${label} 左移`}
                    disabled={idx === 0}
                    onClick={() => moveTab(idx, -1)}
                    className="px-1 text-[11px] text-muted-foreground/50 transition-colors hover:text-midas-red disabled:opacity-25"
                  >
                    ◀
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (k === DOTT_TAB) {
                        setView('dott')
                      } else {
                        setView('strategy')
                        onStrategyChange(k)
                      }
                    }}
                    className={cn(
                      'relative rounded-md border px-3 py-1 text-xs transition-colors',
                      active
                        ? 'border-midas-red bg-midas-red-glow text-midas-red'
                        : 'border-paper text-muted-foreground hover:border-midas-red/40 hover:text-foreground',
                    )}
                  >
                    {label}
                    {isRecommended && <span className="ml-1 text-[10px] text-gold">★荐</span>}
                  </button>
                  <button
                    type="button"
                    aria-label={`${label} 右移`}
                    disabled={idx === tabs.length - 1}
                    onClick={() => moveTab(idx, 1)}
                    className="px-1 text-[11px] text-muted-foreground/50 transition-colors hover:text-midas-red disabled:opacity-25"
                  >
                    ▶
                  </button>
                </div>
              )
            })}
          </div>

          {/* 内容区 · 做T 视图 → 布林结构(★Pro 门控:非 Pro 显 ProLock · 同策略信号/AI卡)·
              策略视图 → 信号(Pro 门控)· crypto 未开策略信号时选中策略 → 提示开开关 */}
          {view === 'dott' ? (
            hasAccess ? (
              <DottStructureView query={bollStructure} />
            ) : (
              <ProLock title="布林做T结构" />
            )
          ) : enabled ? (
          <>
          {/* AI 推荐理由 */}
          {rec && (
            <p className="text-[11px] text-gold/90">
              AI 推荐:{STRATEGY_LABELS[rec.recommended_strategy]} · {rec.reason}
            </p>
          )}

          {/* 当前触发 / 历史信号 · Pro 门控(非 Pro → 后端 locked 空壳 → 遮罩两道门)*/}
          {signals.data?.locked ? (
            <ProLock title="实战策略信号" />
          ) : (
          <>
          {/* 当前触发状态(① 含触发价) */}
          <TriggerStatus
            triggered={sig?.current_triggered ?? false}
            last={sig?.last_signal ?? null}
            market={market}
            hasSignals={(sig?.signals.length ?? 0) > 0}
          />

          {/* ② 历史信号列表(可折叠 · 复盘该策略历史买卖信号点 · 纯数据展示 · 不加建议/风险废话) */}
          {sig && sig.signals.length > 0 && (
            <details className="group rounded-md border border-paper bg-background/50">
              <summary className="cursor-pointer px-2.5 py-1.5 text-[11px] text-muted-foreground/80 hover:text-foreground">
                历史信号 {sig.signals.length} 个 · 点击展开复盘
              </summary>
              <div className="max-h-44 overflow-y-auto border-t border-paper/60">
                {[...sig.signals].reverse().map((s, i) => {
                  const isBuy = s.kind === 'buy'
                  const hasDetail = Object.keys(s.levels).length > 0 || s.strength_note
                  return (
                    <div
                      key={`${s.ts}-${i}`}
                      className="px-2.5 py-1 text-[11px] odd:bg-background/30"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-20 shrink-0 font-mono text-muted-foreground/60">
                          {fmtSignalTs(s.ts)}
                        </span>
                        <span
                          className={cn('shrink-0 font-mono font-medium', isBuy ? 'text-up' : 'text-down')}
                        >
                          {isBuy ? '买' : '卖'} {fmtSignalPrice(s.price, market)}
                        </span>
                        <span className="flex-1 truncate text-right text-muted-foreground/60">
                          {s.reason}
                        </span>
                      </div>
                      {/* ⑤ 关键价位 + ⑥ 成色(批2)· 成色 ma_cross 为 null → 不显示(诚实不空塞)*/}
                      {hasDetail && (
                        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 pl-[5.5rem] text-[10px] text-muted-foreground/50">
                          {Object.keys(s.levels).length > 0 && (
                            <span className="font-mono">{fmtLevels(s.levels)}</span>
                          )}
                          {s.strength_note && <span className="text-gold/70">成色 · {s.strength_note}</span>}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </details>
          )}
          </>
          )}
          </>
          ) : (
            <p className="rounded-md border border-paper bg-background/50 px-2.5 py-1.5 text-[11px] text-muted-foreground/70">
              开启上方「策略信号」开关 · 在 K 线标注买卖点 + 复盘历史信号
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * 布林做T结构视图(做T B-2 重构 · 原 DotTStructureSection 内容搬入此 tab)。
 * ★层级标注「布林结构」(化解两块手表 · 区别 AI 决策卡综合研判)· 倾向复用 biasTone 涨跌色 ·
 *   倾向只偏多/偏空/中性 · 纯展示不下单 · ★免责已移除(依赖全站统一提示)。免费层(不门控)。
 */
function DottStructureView({ query }: { query: UseQueryResult<BollStructureResponse> }) {
  const it = query.isSuccess && query.data.available ? query.data.item : null
  return (
    <div className="rounded-md border border-paper bg-background/50 px-2.5 py-2">
      {query.isPending && <p className="text-[11px] text-muted-foreground/60">载入中…</p>}
      {query.isError && (
        <p className="text-[11px] text-muted-foreground/60">暂时无法读取做T结构</p>
      )}
      {query.isSuccess && !query.data.available && (
        <p className="text-[11px] text-muted-foreground/60">该币暂无做T结构数据</p>
      )}
      {it && (
        <div className="space-y-1.5 text-sm">
          {/* ★布林结构:倾向(层级标注 + 涨跌色偏好 · 区别于 AI 决策卡综合研判)*/}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-muted-foreground">布林结构:</span>
            <span className={cn('font-bold', biasTone(it.bias))}>{it.bias}</span>
            <span className="text-xs text-muted-foreground/70">· {it.state_label}</span>
            {it.transition && it.transition_from && (
              <span className="rounded bg-midas-red-glow/50 px-1.5 py-0.5 text-[10px] font-medium text-midas-red">
                刚转换
              </span>
            )}
          </div>
          {/* 通道位置 %B + zone */}
          <div className="text-xs text-muted-foreground/80">
            通道位置 %B={it.pct_b.toFixed(2)}（{it.zone_label}）
          </div>
          {/* 布林三轨 + 现价 */}
          <div className="font-mono text-xs text-muted-foreground/80">
            上 {fmtN(it.upper)} / 中 {fmtN(it.mid)} / 下 {fmtN(it.lower)} · 现价 {fmtN(it.close)}
          </div>
          {/* 状态转换路径 */}
          {it.transition && it.transition_from && (
            <div className="text-xs text-muted-foreground/60">
              转换:{it.transition_from} → {it.state_label}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TriggerStatus({
  triggered,
  last,
  market,
  hasSignals,
}: {
  triggered: boolean
  last: StrategySignal | null
  market: Market
  hasSignals: boolean
}) {
  if (!hasSignals || !last) {
    return (
      <div className="rounded-md border border-paper bg-background/50 px-2.5 py-1.5 text-[11px] text-muted-foreground/70">
        近期无信号
      </div>
    )
  }
  const isBuy = last.kind === 'buy'
  const tone = isBuy ? 'text-up' : 'text-down'
  const label = isBuy ? '买点' : '卖点'
  // ① 触发价(纯数据 · 带市场符号)
  const priceStr = ` ${fmtSignalPrice(last.price, market)}`
  // ⑤ 关键价位(信号点已算值)· ⑥ 成色(只 rsi/boll · ma_cross 为 null → 不显示成色 · 不空塞)
  const levelsStr = Object.keys(last.levels).length > 0 ? fmtLevels(last.levels) : ''
  return (
    <div
      className={cn(
        'rounded-md border px-2.5 py-1.5 text-[11px]',
        triggered
          ? isBuy
            ? 'border-up/40 bg-up/10'
            : 'border-down/40 bg-down/10'
          : 'border-paper bg-background/50',
      )}
    >
      {triggered ? (
        <span className={cn('font-medium', tone)}>🔔 当前触发:{label}{priceStr} · {last.reason}</span>
      ) : (
        <span className="text-muted-foreground/70">
          最近信号:<span className={tone}>{label}{priceStr}</span> · {last.reason}
        </span>
      )}
      {/* ⑤ 关键价位 + ⑥ 成色(批2 · 第二行)· 成色 ma_cross 为 null → 整段不显示成色(诚实不空塞)*/}
      {(levelsStr || last.strength_note) && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-muted-foreground/60">
          {levelsStr && <span className="font-mono">{levelsStr}</span>}
          {last.strength_note && <span className="text-gold/80">成色 · {last.strength_note}</span>}
        </div>
      )}
    </div>
  )
}
