'use client'

/**
 * AI 沙盘助手 · /lab/assistant(原「结构分析助手」· 路由保留只改显示名)。
 *
 * 自然语言提问 → POST /structure/diagnose(后端:意图归一→7因子快照→单次LLM→validator)
 * → 结论先行四层渲染(照 lab-report 范式:结论卡 / 指标卡 grid / 脚注 section / details 下钻)。
 *
 * 🔴 红线:纯客观结构描述 —— 非价格预测 · 不下单(后端 prompt 三红线焊死);
 *    分析工具非虚拟下单 UI → 不挂 VIRTUAL 徽章(P5 口径),底部保留一行定位声明。
 */

import { useSession } from 'next-auth/react'
import { useState } from 'react'

import { FactorCard } from '@/components/lab/factor-card'
import { ForceBar } from '@/components/lab/force-bar'
import { LabNav } from '@/components/lab/lab-nav'
import { StructureGraph } from '@/components/lab/structure-graph'
import type { SparkPoint } from '@/components/lab/sparkline'
import { SymbolSuggest } from '@/components/lab/symbol-suggest'
import { TopNav } from '@/components/layout/top-nav'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState } from '@/components/ui/state'
import {
  useBasisSeries,
  useFundingRate,
  useLongShortRatio,
  useOpenInterest,
} from '@/hooks/use-crypto'
import { useStructureDiagnose } from '@/hooks/use-structure'
import type { IntentKind, StructureDiagnosis, StructureSnapshot } from '@/lib/api/structure'
import { FACTOR_LABEL } from '@/lib/structure-graph'
import {
  CALIBER_NOTE,
  type Tone,
  buildFactorCards,
  factorHeadline,
  sparklineSpec,
} from '@/lib/structure-viz'
import { cn } from '@/lib/utils'

const INTENT_LABEL: Record<IntentKind, string> = {
  long_crowding: '多头拥挤度',
  short_crowding: '空头拥挤度',
  leverage_buildup: '杠杆堆积',
  funding_extreme: '资金费率状态',
  overall: '整体结构',
}

// 快捷问题(点击即提问 · 用当前 symbol)
const QUICK_QUESTIONS = [
  '多头是不是太拥挤',
  '空头会不会被挤爆',
  '杠杆堆积情况怎么样',
  '资金费率现在极端吗',
  '整体结构看一下',
] as const

export default function LabAssistantPage() {
  const { status: authStatus } = useSession()
  const diagnose = useStructureDiagnose()

  const [symbol, setSymbol] = useState('BTCUSDT')
  const [question, setQuestion] = useState('')

  function ask(q: string) {
    const trimmed = q.trim()
    if (!trimmed || symbol.trim() === '') return
    setQuestion(trimmed)
    diagnose.mutate({ symbol: symbol.trim().toUpperCase(), question: trimmed })
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="mx-auto w-full max-w-5xl px-6 py-8">
        {/* v1.1:大标题删除 —— TopNav「策略研究室」高亮 + LabNav 已标明位置,第三遍重复是噪声 */}
        <LabNav />

        {authStatus === 'unauthenticated' ? (
          <EmptyState title="请先登录" hint="AI 沙盘助手需要登录后访问" />
        ) : (
          <>
            {/* ── 提问区 ──────────────────────────────────────────── */}
            <section className="mb-8 rounded-lg border border-paper bg-cream p-5 shadow-sm">
              <h2 className="mb-4 font-serif text-lg font-bold">向助手提问</h2>
              <div className="flex flex-col gap-3 md:flex-row">
                {/* symbol 联想(输 eth → 下拉 ETHUSDT)· 无匹配可直输,后端补后缀兜底 */}
                <SymbolSuggest value={symbol} onChange={setSymbol} className="md:w-44" />
                <Input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') ask(question)
                  }}
                  placeholder="如:BTC 现在多头是不是太拥挤?"
                  className="flex-1"
                />
                <Button
                  onClick={() => ask(question)}
                  disabled={diagnose.isPending || question.trim() === '' || symbol.trim() === ''}
                >
                  {diagnose.isPending ? '分析中…' : '结构诊断'}
                </Button>
              </div>
              {/* 快捷问题 */}
              <div className="mt-3 flex flex-wrap gap-2">
                {QUICK_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => ask(q)}
                    disabled={diagnose.isPending}
                    className="rounded-full border border-paper px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-midas-red hover:text-midas-red disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
              {diagnose.isError && (
                <p className="mt-3 text-sm text-midas-red">{diagnose.error.message}</p>
              )}
              <p className="mt-3 text-xs text-faint">
                覆盖 USDT 永续 · 7 因子(多空比 / taker / OI / 资金费率 / 基差 / 情绪)·
                数据窗口最长 60 天。
              </p>
            </section>

            {/* ── 诊断结果 · 结论先行四层 ──────────────────────────── */}
            {diagnose.data && <DiagnosisResult diag={diagnose.data} />}
          </>
        )}

        {/* 定位声明(P5 口径:分析工具非虚拟下单 UI · 无 VIRTUAL 徽章 · 保留一行定位)*/}
        <footer className="mt-10 border-t border-paper pt-4 text-xs text-faint">
          本助手仅描述当前市场结构,非价格预测,不构成投资建议。
        </footer>
      </main>
    </div>
  )
}

// ── 大数字面板(刀2 · 关键指标竖排 · 全部 snapshot 结构化取数)──────────────
// 三期批1 换血:basis 出(信息保留在图谱节点+因子卡)· funding_zscore 进(极端程度一眼指标)
const BIG_NUMBER_FACTORS = [
  { key: 'funding_rate', label: '资金费率' },
  { key: 'account_long_short', label: '大户账户多空比' },
  { key: 'open_interest', label: 'OI 24h 变化' },
  { key: 'funding_zscore', label: '费率 Z 分数(60d)' },
] as const

const TONE_TEXT: Record<Tone, string> = {
  bull: 'text-up', bear: 'text-down', neutral: 'text-muted-foreground',
}

function BigNumberPanel({ snapshot }: { snapshot: StructureSnapshot }) {
  return (
    <div className="flex h-full flex-col justify-center gap-3 rounded-lg border border-paper bg-cream p-4 shadow-sm">
      {BIG_NUMBER_FACTORS.map(({ key, label }) => {
        const head = factorHeadline(key, snapshot)
        return (
          <div key={key}>
            <div className="text-xs text-muted-foreground">{label}</div>
            <div
              className={cn(
                'font-mono text-2xl font-bold tabular-nums',
                head ? TONE_TEXT[head.tone] : 'text-muted-foreground/50',
              )}
            >
              {head?.text ?? '—'}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── 四层渲染(照 lab-report 范式)────────────────────────────────────────────
function DiagnosisResult({ diag }: { diag: StructureDiagnosis }) {
  // sparkline 数据旁路:crypto 现有端点(🔴 不进诊断链 · services/structure 零碰)。
  // hooks 固定提升到本层(React 规则:不能在 factor map 循环里调)· 窗口对齐 snapshot 口径。
  const symbol = diag.snapshot.symbol
  const lsr = useLongShortRatio(symbol, 288) // 5min×288 = 24h · 喂 3 个多空类因子卡
  const oi = useOpenInterest(symbol, 288)
  const funding = useFundingRate(symbol, 21) // 8h×21 = 7d
  const basis = useBasisSeries(symbol, 288)

  // 因子 key → sparkline 序列(三期批1:global 有时序 · 预测费率/z-score/OI比为单值 → null 文字降级)
  function seriesFor(factor: string): SparkPoint[] | null {
    const lsrItems = lsr.data?.items ?? []
    switch (factor) {
      case 'account_long_short':
        return lsrItems.map((p) => ({ t: p.ts, v: p.top_account_ratio }))
      case 'position_long_short':
        return lsrItems.map((p) => ({ t: p.ts, v: p.top_position_ratio }))
      case 'taker_flow':
        return lsrItems.map((p) => ({ t: p.ts, v: p.taker_ratio }))
      case 'global_long_short':
        // 刀C global 列(④卡同源)· 过滤 0 = 未采哨兵老行
        return lsrItems
          .filter((p) => p.global_account_ratio > 0)
          .map((p) => ({ t: p.ts, v: p.global_account_ratio }))
      case 'open_interest':
        return (oi.data?.items ?? []).map((p) => ({ t: p.ts, v: p.oi_usd }))
      case 'funding_rate':
        return (funding.data?.items ?? []).map((p) => ({ t: p.ts, v: p.rate }))
      case 'basis':
        return (basis.data?.items ?? []).map((p) => ({ t: p.ts, v: p.basis_pct }))
      default:
        return null
    }
  }

  const accountRatio = diag.snapshot.account_long_short?.value?.latest
  // 批1 修复刀:卡区 snapshot 驱动(FACTOR_ORDER 排序 · 与图谱一致)
  const factorCards = buildFactorCards(diag.snapshot, diag.factor_findings)

  return (
    <div className="space-y-8">
      {/* ① 结论先行卡(抄 lab-report 结论卡 markup)*/}
      <section>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h2 className="font-serif text-lg font-bold">结构诊断</h2>
          <span className="rounded bg-midas-red-glow px-2 py-0.5 font-mono text-[11px] text-midas-red">
            {INTENT_LABEL[diag.intent]}
          </span>
        </div>
        {/* v1.1:删 symbol·perp·时间戳元信息行(Hans 反馈无效信息 · symbol 在输入框已示)*/}
        <div className="mt-3 rounded-lg border border-paper bg-cream p-4 shadow-sm">
          <p className="text-sm leading-relaxed text-foreground">{diag.conclusion}</p>
          {/* 多空力量对比条(snapshot 已有字段旁路展示 · 比值非法/缺失自动不渲染) */}
          {accountRatio != null && (
            <ForceBar ratio={accountRatio} sourceLabel="大户账户多空比 · latest" />
          )}
        </div>
      </section>

      {/* ①.5 结构沙盘 · 图谱 + 大数字面板并排(刀2 重排:lg 左 3/5 图谱 · 右 2/5 数字;md 以下纵排)*/}
      <section>
        <h2 className="mb-3 font-serif text-lg font-bold">结构沙盘</h2>
        <div className="grid gap-4 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <StructureGraph snapshot={diag.snapshot} findings={diag.factor_findings} />
          </div>
          <div className="lg:col-span-2">
            <BigNumberPanel snapshot={diag.snapshot} />
          </div>
        </div>
      </section>

      {/* ② 因子状态卡(批1 修复刀:snapshot 驱动 —— LLM 没点名的因子也出卡,
          有 finding 附判定、无 finding 降级为数值+图 · 如实留白不伪造判定)*/}
      {factorCards.length > 0 && (
        <section>
          <h2 className="mb-3 font-serif text-lg font-bold">分因子状态</h2>
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-3">
            {factorCards.map((c) => {
              const spec = sparklineSpec(c.key, diag.snapshot)
              return (
                <FactorCard
                  key={c.key}
                  finding={c.finding}
                  label={FACTOR_LABEL[c.key] ?? c.key}
                  window={c.window}
                  series={seriesFor(c.key)}
                  headline={factorHeadline(c.key, diag.snapshot)}
                  sparkStroke={spec.stroke}
                  sparkBaseline={spec.baseline}
                />
              )
            })}
          </div>
        </section>
      )}

      {/* ③ 口径 / 缺失说明(抄脚注 section markup)*/}
      <section className="rounded-lg border border-paper bg-surface-subtle p-4">
        <h2 className="mb-2 font-serif text-sm font-bold">数据口径</h2>
        {/* 批1 修复刀:口径文案抽常量(与 prompts 红线三对齐 · vitest 断言防再漂移) */}
        <p className="text-xs text-muted-foreground">{CALIBER_NOTE}</p>
        {diag.unsupported_note && (
          <p className="mt-2 text-xs text-gold">⚠ {diag.unsupported_note}</p>
        )}
      </section>

      {/* ④ 快照下钻(抄 details+pre markup)*/}
      <section className="rounded-lg border border-paper bg-surface-subtle p-4">
        <details>
          <summary className="cursor-pointer text-xs text-muted-foreground/70">
            展开 7 因子原始快照(数据下钻)
          </summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded bg-cream p-3 font-mono text-[11px] text-muted-foreground">
            {JSON.stringify(diag.snapshot, null, 2)}
          </pre>
        </details>
      </section>
    </div>
  )
}
