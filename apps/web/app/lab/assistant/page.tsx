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
import type { IntentKind, StructureDiagnosis } from '@/lib/api/structure'

// 因子键名 → 中文(因子状态卡标题用)
const FACTOR_LABEL: Record<string, string> = {
  account_long_short: '大户账户多空比',
  position_long_short: '大户持仓多空比',
  taker_flow: 'taker 主动买卖',
  open_interest: '未平仓量(OI)',
  funding_rate: '资金费率',
  basis: '基差',
  sentiment: '市场情绪',
}

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

// ── 四层渲染(照 lab-report 范式)────────────────────────────────────────────
function DiagnosisResult({ diag }: { diag: StructureDiagnosis }) {
  // sparkline 数据旁路:crypto 现有端点(🔴 不进诊断链 · services/structure 零碰)。
  // hooks 固定提升到本层(React 规则:不能在 factor map 循环里调)· 窗口对齐 snapshot 口径。
  const symbol = diag.snapshot.symbol
  const lsr = useLongShortRatio(symbol, 288) // 5min×288 = 24h · 喂 3 个多空类因子卡
  const oi = useOpenInterest(symbol, 288)
  const funding = useFundingRate(symbol, 21) // 8h×21 = 7d
  const basis = useBasisSeries(symbol, 288)

  // 因子 key → sparkline 序列(sentiment 无现成时序 hook → null 留文字 · 优雅降级)
  function seriesFor(factor: string): SparkPoint[] | null {
    const lsrItems = lsr.data?.items ?? []
    switch (factor) {
      case 'account_long_short':
        return lsrItems.map((p) => ({ t: p.ts, v: p.top_account_ratio }))
      case 'position_long_short':
        return lsrItems.map((p) => ({ t: p.ts, v: p.top_position_ratio }))
      case 'taker_flow':
        return lsrItems.map((p) => ({ t: p.ts, v: p.taker_ratio }))
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

      {/* ② 因子状态卡(FactorCard:state/detail/window + sparkline + 背离金框)*/}
      {diag.factor_findings.length > 0 && (
        <section>
          <h2 className="mb-3 font-serif text-lg font-bold">分因子状态</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {diag.factor_findings.map((f) => (
              <FactorCard
                key={`${f.factor}-${f.state}`}
                finding={f}
                label={FACTOR_LABEL[f.factor] ?? f.factor}
                series={seriesFor(f.factor)}
              />
            ))}
          </div>
        </section>
      )}

      {/* ③ 口径 / 缺失说明(抄脚注 section markup)*/}
      <section className="rounded-lg border border-paper bg-surface-subtle p-4">
        <h2 className="mb-2 font-serif text-sm font-bold">数据口径</h2>
        <p className="text-xs text-muted-foreground">
          各因子结论均限定其数据窗口(24h / 7d / latest);本系统因子历史最长 60 天,
          「极值/分位」类表述均为近 N 天内口径,非长期历史基线。
          清算数据、盘口深度、全市场人数比暂未采集。
        </p>
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
