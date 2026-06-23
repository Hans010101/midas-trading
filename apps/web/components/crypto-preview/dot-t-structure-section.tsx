'use client'

/**
 * 做T结构模块(做T B-2)· 详情页展示单币布林 6 态结构 · 读 B-1 /crypto/boll-structure/{symbol}。
 *
 * ★化解「两块手表」:这是【布林结构层】的客观结构 + 单指标倾向(标注「布林结构:偏多」),
 *   区别于 AI 决策卡的【多维综合研判】(本刀不碰 AI 卡)。免费层(同 A-2 列表 · B-1 接口均不门控 ·
 *   与策略信号 overlay 的 Pro 门控无关)。
 * ★受做T开关 dott 控制显隐(默认关 · 主动开的用户才看到)· dott 关 → 不渲染也不取数。
 * ★纯展示不碰交易 · 倾向只偏多/偏空/中性(复用 A-2 biasTone 涨跌色,不写死红绿)· 底部免责。
 * 轻量克制:几行结构,非屏幕杀手。
 */

import { useState } from 'react'

import { biasTone } from '@/components/crypto/boll-scan-list'
import { fetchBollStructure } from '@/lib/api/crypto-market'
import { readDisplayPrefs } from '@/lib/display-prefs'
import { cn } from '@/lib/utils'
import { useQuery } from '@tanstack/react-query'

function fmtN(n: number): string {
  if (n >= 1) return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return n.toFixed(4)
}

export function DotTStructureSection({ futuresSymbol }: { futuresSymbol: string }) {
  // ★dott 控制显隐(默认关)· 同步读 cookie(客户端渲染 · 同刀2)
  const [dott] = useState(() => readDisplayPrefs().indicators.dott)

  const q = useQuery({
    queryKey: ['boll-structure', futuresSymbol],
    queryFn: ({ signal }) => fetchBollStructure(futuresSymbol, signal),
    enabled: dott, // ★dott 关 → 不取数
    retry: 0,
    staleTime: 60_000,
  })

  if (!dott) return null // ★做T开关关 → 模块不显示

  const disclaimer = q.data?.disclaimer ?? '结构描述非建议 · 仅供参考,不构成投资建议'
  const it = q.isSuccess && q.data.available ? q.data.item : null

  return (
    <section className="rounded-lg border border-paper bg-surface-card p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-serif text-sm font-bold text-foreground">做T结构</span>
        {/* ★层级标注:布林结构层(化解两块手表 · 区别 AI 决策卡综合研判)*/}
        <span className="rounded bg-midas-red-glow/40 px-1.5 py-0.5 text-[10px] font-medium text-midas-red">
          布林结构层
        </span>
      </div>

      {q.isPending && <p className="text-xs text-muted-foreground/60">载入中…</p>}
      {q.isError && <p className="text-xs text-muted-foreground/60">暂时无法读取做T结构</p>}
      {q.isSuccess && !q.data.available && (
        <p className="text-xs text-muted-foreground/60">该币暂无做T结构数据</p>
      )}

      {it && (
        <div className="space-y-1.5 text-sm">
          {/* ★布林结构:倾向(层级标注 + 涨跌色偏好 · 区别于平级综合结论)*/}
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

      {/* 底部免责(接口返回 · 红线)*/}
      <p className="mt-3 text-[11px] text-muted-foreground/60">{disclaimer}</p>
    </section>
  )
}
